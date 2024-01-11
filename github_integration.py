import base64
import io
import requests
import json
import csv
import re
from io import StringIO

def getFiles(github_api_key, github_owner, github_repo, github_branch):

    url = "https://api.github.com/repos/" + github_owner + "/" + github_repo + "/git/trees/" + github_branch + "?recursive=1"
    payload={}
    headers = {
    'Authorization': 'Bearer ' + github_api_key,
    }
    response = requests.request("GET", url, headers=headers, data=payload)
    return json.loads(response.text)


def get_file_data(github_api_key, github_owner, github_repo, file_path):
    url = "https://api.github.com/repos/" + github_owner + "/" + github_repo + "/contents/" + file_path
    payload={}
    headers = {
    'Authorization': 'Bearer ' + github_api_key
    }
    response = requests.request("GET", url, headers=headers, data=payload)
    return json.loads(response.text)

def readFiles(github_api_key, github_owner, github_repo, github_branch, viewId, apiKey):
    repo_files = getFiles(github_api_key, github_owner, github_repo, github_branch)
    headers = {
    'X-GitHub-Api-Version': '2022-11-28',
    'Authorization': 'Bearer ' + github_api_key
    }
    for repo_file in repo_files['tree']:
        if repo_file['path'].endswith('.csv'):
            valid_file = get_file_data(github_api_key, github_owner, github_repo, repo_file['path'])
            url = valid_file['download_url']
            req = requests.get(url, headers=headers)        
            print(url)
            print(req)
            if req.status_code == requests.codes.ok:
                generate_columns(viewId, apiKey, req.text)
                cs_with_path = add_pathtag_to_csv(req.text, valid_file['path'])
                upload_file_into_gridly(cs_with_path, viewId, apiKey)
            else:
                print('Content was not found.')

def add_pathtag_to_csv(csv_string, path):
    # Parse the CSV string into a list of rows
    rows = list(csv.reader(csv_string.splitlines()))
    firstRow = True
    # Add a new column with the value 7 for all rows
    for row in rows:
        if firstRow:
            row.append('_pathTag')
            firstRow = False
        else:
            row.append(path)
    # Generate a new CSV string with the modified rows
    modified_csv_string = "\n".join(["\t".join(row) for row in rows])
    return modified_csv_string


def upload_file_into_gridly(file_content, viewId, apiKey):
    url = "https://api.gridly.com/v1/views/"+viewId+"/import"
    payload={}
    files=[
    ('file',('Test Database NS_MT Post Edit_Default view.csv',file_content,'text/csv'))
    ]
    headers = {
    'Authorization': 'ApiKey ' + apiKey
    }
    response = requests.request("POST", url, headers=headers, data=payload, files=files)

def generate_columns(view_id, apiKey, csv_file):
    reader = csv.DictReader(csv_file.splitlines())
    # Get the headers
    headers = reader.fieldnames

    for header in headers:
        url = "https://api.gridly.com/v1/views/"+view_id+"/columns"
        id = re.sub('[^0-9a-zA-Z]+', '*', header)
        payload = json.dumps({
            "id": id,
            "isTarget": True,
            "name": header,
            "type": "multipleLines"
        })
        headers = {
        'Authorization': 'ApiKey ' + apiKey,
        'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=payload)

        #print(response.text) 

def get_files_from_github(event, context):
    gridly_api_key = event["gridly_api_key"]
    view_id = event["view_id"]
    github_owner = event["github_owner"]
    github_token = event["github_token"]
    github_repo = event["gitub_repo"]
    github_branch = event["github_branch"]
    readFiles(github_token, github_owner, github_repo, github_branch, view_id, gridly_api_key)


def export_file_from_gridly(view_id, apikey):

    url = "https://api.gridly.com/v1/views/" + view_id + "/export"

    payload={}
    headers = {
    'Authorization': 'ApiKey ' + apikey
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    return response.text

def split_csv_by_path(csv_string):

    reader = csv.DictReader(csv_string.splitlines())
    rows = list(reader)

    # Create a dictionary of lists, with one list for each unique value in the given column
    csv_dict = {}
    for row in rows:
        if row['_pathTag'] not in csv_dict:
            csv_dict[row['_pathTag']] = [row]
        else:
            csv_dict[row['_pathTag']].append(row)

    # Write each list of dictionaries to a separate CSV string
    csv_strings = {}
    fieldnames = ['English', 'Swedish', 'Vietnamese', '_recordId', '_pathTag']

    for name, rows in csv_dict.items():
        # Use a StringIO object to write the CSV to a string
        sio = StringIO()
        writer = csv.DictWriter(sio, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
        csv_strings[name] = sio.getvalue()
    return csv_strings

def delete_not_needed_headers(csv_string):
    csv_string_io = io.StringIO(csv_string)
    reader = csv.DictReader(csv_string_io, delimiter='\t')
    rows = [row for row in reader]
    column_to_delete = '_pathTag'
    for row in rows:
        del row[column_to_delete]
    output_string = io.StringIO()
    writer = csv.DictWriter(output_string, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output_string.getvalue()

def fetch_to_github_steps(github_api_key, github_owner, github_repo, view_id, api_key):
    files = split_csv_by_path(export_file_from_gridly(view_id, api_key))
    for name, csv_string in files.items():
        csv_string = delete_not_needed_headers(csv_string)
        file_data = get_file_data(github_api_key, github_owner, github_repo, name)
        commit_to_github(github_api_key, github_owner, github_repo, name, csv_string, file_data['sha'])

def commit_to_github(github_api_key, github_owner, github_repo, file_path, content, sha):
    url = "https://api.github.com/repos/"+github_owner+"/" + github_repo + "/contents/" + file_path
    content = base64.b64encode(bytes(content, 'utf-8'))
    print(content)
    payload = json.dumps({
    "message": "Update from Gridly",
    "content": content.decode('utf-8'),
    "sha": sha
    })
    headers = {
    'Authorization': 'Bearer ' + github_api_key,
    'Content-Type': 'application/json'
    }

    response = requests.request("PUT", url, headers=headers, data=payload)
    print(response.text)

def commit_files_to_github(event, context):
    gridly_api_key = event["gridly_api_key"]
    view_id = event["view_id"]
    github_owner = event["github_owner"]
    github_token = event["github_token"]
    github_repo = event["gitub_repo"]
    github_branch = event["github_branch"]
    fetch_to_github_steps(github_token, github_owner, github_repo, view_id, gridly_api_key)

