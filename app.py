import os
import json
import re
from slack import WebClient
from flask import Flask, request, jsonify, Response
from slackeventsapi import SlackEventAdapter
import sqlite3
import gspread
from google.oauth2.service_account import Credentials
import threading
import requests
import time
import datetime

DATABASE = 'knowledge-crow'
app = Flask(__name__)
# Initialize Slack WebClient and Event Adapter
slack_token = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=slack_token)
azure_url = os.environ["AZURE_URL"]
azure_auth_key = os.environ["AZURE_API_KEY"]

slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)

def create_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gsheetmapping (
            Team TEXT PRIMARY KEY,
            Sheetlink TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Create the table on startup
create_table()

def connect_team_runbook(team_id, google_sheet_link):
    with app.app_context():
        try:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO gsheetmapping (Team, Sheetlink)
                VALUES (?, ?)
            ''', (team_id, google_sheet_link))
            conn.commit()
            conn.close()
            return "created", 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# Get a specific message by ID
def get_team_runbook(team_id):
    with app.app_context():
        try:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM gsheetmapping WHERE Team = ?', (team_id,))
            message = cursor.fetchone()
            conn.close()
            if message:
                return message[1], 200
            else:
                return jsonify({"error": "Message not found"}), 404
        except Exception as e:
            print(str(e))
            return jsonify({"error": str(e)}), 500

# Delete a message by ID
def disconnect_team_runbook(team_id):
    with app.app_context():
        try:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM gsheetmapping WHERE team = ?', (team_id,))
            conn.commit()
            conn.close()
            return "deleted", 204
        except Exception as e:
            print(str(e))
            return jsonify({"error": str(e)}), 500

def extract_sheet_id(sheets_link):
    pattern = r'/d/([a-zA-Z0-9-_]+)'
    match = re.search(pattern, sheets_link)
    if match:
        return match.group(1)
    else:
        return None

def sendBotReply(channel, text, thread_ts):
    if thread_ts is not None:
        client.chat_postMessage(channel=channel, text=text, thread_ts = thread_ts)
    else:
        client.chat_postMessage(channel=channel, text=text)
def getTopicAndTeamForSaveAction(text):
    parts = text.split("title=")
    if len(parts) == 1:
        spaceSepWords = text.split()
        return spaceSepWords[2], None
    spaceSepWords = parts[0].split()
    return spaceSepWords[2], parts[1]

def generate_user_names(messages):
    user_dict = {}
    user_counter = 1
    
    for message in messages:
        user_id = message.get("user")
        if user_id not in user_dict:
            user_dict[user_id] = f"user{user_counter}"
            user_counter += 1
    
    return user_dict

def save(event):
    with app.app_context():
        text = event["text"]
        channel = event["channel"]
        if event.get("subtype") is None and "thread_ts" in event:
            thread_ts = event.get("thread_ts")
            team_id, title = getTopicAndTeamForSaveAction(text)
            if title is None:
                title = "important thread"
            try:
                result = client.conversations_replies(channel=channel, ts=thread_ts)
                messages = result["messages"]
                userIdMap = generate_user_names(messages=messages)
                chat = [{"user": userIdMap.get(message.get("user", ""), "user-x"), "text": message.get("text", "")} for message in messages]
                chat = chat[:-1]
                azureReqBody = convertToAzureFormat(chat)
                headers = {"Content-Type":"application/json", "Ocp-Apim-Subscription-Key":azure_auth_key}
                respUrl = callAzureML(azure_url,azureReqBody, {}, headers)
                link, status = get_team_runbook(team_id)
                if status != 200:
                    sendBotReply(channel=channel, text = "There was a issue getting the sheet link!", thread_ts=event.get("thread_ts"))
                    # resp = Response(response="There was a issue getting the sheet link!", status=200,  mimetype="application/json")
                    # resp.headers['Access-Control-Allow-Origin'] = '*'
                    # return resp
                    return
                sheet_key = extract_sheet_id(link)
                convoDetails = client.chat_getPermalink(channel=channel, message_ts=thread_ts)
                chat_link = convoDetails['permalink']
                time.sleep(3)
                summary = getAzureMLResp(url = respUrl, headers = headers)
                _, status = add_data_to_google_sheets(sheet_key, title, chat_link, summary)
                if status !=200:
                    sendBotReply(channel=channel, text = "unable to update google sheets!", thread_ts=event.get("thread_ts"))
                    return
                    # resp = Response(response="ok", status=200,  mimetype="application/json")
                    # resp.headers['Access-Control-Allow-Origin'] = '*'
                    # return resp
                sendBotReply(channel=channel, text = "Recorded!", thread_ts=thread_ts)
                return
                # resp = Response(response="ok", status=200,  mimetype="application/json")
                # resp.headers['Access-Control-Allow-Origin'] = '*'
                # return resp
            except Exception as e:
                print(e)
                return
                # resp = Response(response="ok", status=200,  mimetype="application/json")
                # resp.headers['Access-Control-Allow-Origin'] = '*'
                # return resp
        else:
            sendBotReply(channel=channel, text = "knowledgeCrow works only in conversation threads", thread_ts=None)
            return
            # resp = Response(response="ok", status=200,  mimetype="application/json")
            # resp.headers['Access-Control-Allow-Origin'] = '*'
            # return resp

def disconnect(event):
    with app.app_context():
        text = event["text"]
        channel = event["channel"]
        split_string = text.split()
        if len(split_string) < 3:
            sendBotReply(channel=channel, text = "Team name not specified in disconnect!", thread_ts=event.get("thread_ts"))
            # resp = Response(response="ok", status=200,  mimetype="application/json")
            # resp.headers['Access-Control-Allow-Origin'] = '*'
            # return resp
            return
        team_name = split_string[2]
        _, status = disconnect_team_runbook(team_name)
        if status !=204:
            sendBotReply(channel=channel, text = "There was some issue disconnecting, please try again!", thread_ts=event.get("thread_ts"))
            # resp = Response(response="ok", status=200,  mimetype="application/json")
            # resp.headers['Access-Control-Allow-Origin'] = '*'
            # return resp
            return
        sendBotReply(channel=channel, text = f"{team_name}'s sheet disconnected!", thread_ts=event.get("thread_ts"))
        return

def getLink(event):
    with app.app_context():
        text = event["text"]
        channel = event["channel"]
        split_string = text.split()
        if len(split_string) < 3:
            sendBotReply(channel=channel, text = "Team name not specified in get!", thread_ts=event.get("thread_ts"))
            return
        team_name = split_string[2]
        link, status= get_team_runbook(team_name)
        if status != 200:
            sendBotReply(channel=channel, text = "There was a issue getting the sheet link!", thread_ts=event.get("thread_ts"))
            return
        sendBotReply(channel=channel, text = f"Sheet: {link}", thread_ts=event.get("thread_ts"))

def connect(event):
    with app.app_context():
        text = event["text"]
        channel = event["channel"]
        split_string = text.split()
        if len(split_string) < 4:
            sendBotReply(channel=channel, text = "Team name or google sheet link is missing!", thread_ts=event.get("thread_ts"))
            # resp = Response(response="fsadf", status=200,  mimetype="application/json")
            # resp.headers['Access-Control-Allow-Origin'] = '*'
            # return resp
            return
        team_name = split_string[2]
        g_sheet_link = split_string[3]
        _, status = connect_team_runbook(team_name, g_sheet_link)
        if status != 201:
            sendBotReply(channel=channel, text = "There was a issue connecting the sheet!", thread_ts=event.get("thread_ts"))
            # resp = Response(response="issue connecting to sheet", status=200,  mimetype="application/json")
            # resp.headers['Access-Control-Allow-Origin'] = '*'
            # return resp
            return
        sendBotReply(channel=channel, text = f"Sheet connected! Team: {team_name} Sheet: {g_sheet_link}", thread_ts=event.get("thread_ts"))
        return
        
def connect_thread(event):
    with app.app_context():
        connect(event)
    return

def getLink_thread(event):
    with app.app_context():
        getLink(event)
    return

def disconnect_thread(event):
    with app.app_context():
        disconnect(event)
    return

def save_thread(event):
    with app.app_context():
        save(event)
    return

# Define event handler for message events
@slack_events_adapter.on("message")
def message(event_data):
    event = event_data["event"]
    text = event["text"]
    channel = event["channel"]
    isThread = "thread_ts" in event
    if "knowledgeCrow connect" in text:
        #run in background
        
        threading.Thread(target=connect_thread, args=(event,)).start()
        resp = Response(response="success", status=200,  mimetype="application/json")
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    elif "knowledgeCrow get" in text:
        #run in background
        
        threading.Thread(target=getLink_thread, args=(event,)).start()
        resp = Response(response="ok", status=200,  mimetype="application/json")
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    elif "knowledgeCrow disconnect" in text:
        #run in background
        
        threading.Thread(target=disconnect_thread, args=(event,)).start()
        resp = Response(response="ok", status=200,  mimetype="application/json")
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp             
    elif "knowledgeCrow save" in text:
        #run in background
        threading.Thread(target=save_thread, args=(event,)).start()
        resp = Response(response="ok", status=200,  mimetype="application/json")
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp

    resp = Response(response="ok", status=200,  mimetype="application/json")
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

def add_data_to_google_sheets(sheet_key, topic, chat_link, summary):
    # Replace 'your_credentials.json' with the path to your Google Sheets API credentials file
    credentials = Credentials.from_service_account_file('your_credential.json', scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive'])
    gc = gspread.authorize(credentials)
    try:
        # Open the Google Sheets spreadsheet
        spreadsheet = gc.open_by_key(sheet_key)
        worksheet_name = 'Sheet1'
        worksheet = spreadsheet.worksheet(worksheet_name)
        dateStr = datetime.datetime.now().strftime("%B %d, %Y %I:%M%p")
        new_row = [dateStr, topic, chat_link, summary]
        worksheet.append_row(new_row)

        print("Data added to Google Sheets successfully.")
        return "ok", 200
    except Exception as e:
        print(f"Error adding data to Google Sheets: {str(e)}")
        return "failure", 500

def convertToAzureFormat(conversationList):
    conversationItemList=[]
    for idx, item in enumerate(conversationList):
        conversation_item = {
            "text": item["text"],
            "id": str(idx),
            "role": "Agent",
            "participantId": item["user"]
        }
        conversationItemList.append(conversation_item)
    conversationsObj = [{
        "conversationItems": conversationItemList,
        "modality": "text",
        "id": "conversation1",
        "language": "en"
    }]

    analysisInputObj = {"conversations":conversationsObj}

    requestBody = {
        "displayName": "Engineering Discussion",
        "analysisInput": analysisInputObj,
        "tasks": [
            {
            "taskName": "summary",
            "kind": "ConversationalSummarizationTask",
            "parameters": {
                "summaryAspects": ["narrative"],
            }
            }
        ]
    }
    return requestBody

def callAzureML(url, data=None, params = None, headers = None):
    try:
        response = requests.post(url, json=data, params=params, headers=headers)
        # Check if the request was successful (status code 200)
        if response.status_code == 202:
            return response.headers["operation-location"]
        else:
            print(f"POST request failed with status code: {response.status_code}")
    except requests.RequestException as e:
        print("Error sending POST request:", e)

def getAzureMLResp(url, headers):
    try:
        response = requests.get(url, headers=headers)
        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            resp = response.json()
            summaries = resp["tasks"]["items"][0]["results"]["conversations"][0]["summaries"]
            print(resp)
            if len(summaries) == 0:
                return "Summary could not be created by the AI model"
            else:
                return summaries[0]["text"] 
        else:
            print(f"POST request failed with status code: {response.status_code}")
    except requests.RequestException as e:
        print("Error sending GET request:", e)
    return "summary"


# Run the Flask app
if __name__ == "__main__":
    app.run(port=3000, debug=True)