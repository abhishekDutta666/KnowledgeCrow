import os
import json
from slack import WebClient
from flask import Flask, request, jsonify, Response
from slackeventsapi import SlackEventAdapter
import sqlite3
import gspread
import traceback
from google.oauth2.service_account import Credentials
# import requests
# import asyncio

# Initialize Flask app
app = Flask(__name__)

# Database configuration
DATABASE = 'knowledge-crow'

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

def connect_team_runbook(team_id, google_sheet_link):
    data = request.json
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO gsheetmapping (Team, Sheetlink)
            VALUES (?, ?)
        ''', (team_id, google_sheet_link))
        conn.commit()
        conn.close()
        print("created")
        return "created", 201
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

# Get a specific message by ID
def get_team_runbook(team_id):
    print("team id : ", team_id)
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM gsheetmapping WHERE Team = ?', (team_id,))
        message = cursor.fetchone()
        conn.close()
        print(message)
        if message:
            return message
        else:
            return jsonify({"error": "Message not found"}), 404
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

# Delete a message by ID
def disconnect_team_runbook(team_id):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM gsheetmapping WHERE team = ?', (team_id,))
        conn.commit()
        conn.close()
        print("deleted")
        return "deleted"
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500


# Create the table on startup
create_table()
# Initialize Slack WebClient and Event Adapter
slack_token = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=slack_token)
slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)

def sendBotReply(channel, text, thread_ts):
    if thread_ts is not None:
        client.chat_postMessage(channel=channel, text=text, thread_ts = thread_ts)
    else:
        client.chat_postMessage(channel=channel, text=text)
# Define event handler for message events
@slack_events_adapter.on("message")
def message(event_data):
    #print(event_data)
    event = event_data["event"]
    text = event["text"]
    channel = event["channel"]
    isThread = "thread_ts" in event
    if "knowledgeCrow connect" in text:
        split_string = text.split()
        if len(split_string) < 4:
            sendBotReply(channel=channel, text = "Team name or google sheet link is missing!", thread_ts=event.get("thread_ts"))
            return 'OK', 200
        team_name = split_string[2]
        g_sheet_link = split_string[3]
        connect_team_runbook(team_name, g_sheet_link)
        sendBotReply(channel=channel, text = f"Sheet connected!{team_name} {g_sheet_link}", thread_ts=event.get("thread_ts"))
        resp = Response(response=json.dumps(response), status=200,  mimetype="application/json")
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    elif "knowledgeCrow get" in text:
        split_string = text.split()
        if len(split_string) < 3:
            sendBotReply(channel=channel, text = "Team name not specified in get!", thread_ts=event.get("thread_ts"))
            return 'OK', 200
        team_name = split_string[2]
        link = get_team_runbook(team_name)
        sendBotReply(channel=channel, text = f"Sheet value! {link}", thread_ts=event.get("thread_ts"))
        resp = Response(response=json.dumps(response), status=200,  mimetype="application/json")
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    elif "knowledgeCrow disconnect" in text:
        split_string = text.split()
        if len(split_string) < 3:
            sendBotReply(channel=channel, text = "Team name not specified in disconnect!", thread_ts=event.get("thread_ts"))
            return 'OK', 200
        team_name = split_string[2]
        disconnect_team_runbook(team_name)
        sendBotReply(channel=channel, text = f"Sheet disconnected! {team_name}", thread_ts=event.get("thread_ts"))
        resp = Response(response=json.dumps(response), status=200,  mimetype="application/json")
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp             
    elif "knowledgeCrow add" in text:
        if event.get("subtype") is None and isThread:
            thread_ts = event.get("thread_ts")
            #print("passed trigger check")
            try:
                # Get conversation history for the thread
                result = client.conversations_replies(channel=channel, ts=thread_ts)
                messages = result["messages"]
                #print("passed reply retrieval")
                # Extract user information and message text
                summary = [{"user": message.get("user", ""), "text": message.get("text", "")} for message in messages]
                #print("passed summary creation")
                # Prepare JSON response
                response = {
                    "channel_id": channel,
                    "thread_ts": thread_ts,
                    "messages": summary,
                    "ok":"true"
                }
                val = client.chat_postMessage(channel=channel, thread_ts=thread_ts, text = "Recorded!")
                get_team_runbook()
                add_data_to_google_sheets("1hGZvhmaL1LOtEf-lA4TIu5uZfKaiwf6J3HJzowuvCWs", "topic", "some link", "summary")
                #print(response)
                resp = Response(response=json.dumps(response), status=200,  mimetype="application/json")
                resp.headers['Access-Control-Allow-Origin'] = '*'
                return resp
            except Exception as e:
                resp = Response(response=json.dumps(response), status=200,  mimetype="application/json")
                resp.headers['Access-Control-Allow-Origin'] = '*'
                return resp
        else:
            sendBotReply(channel=channel, text = "knowledgeCrow works only in conversation threads", thread_ts=None)
            return 'OK', 200

def add_data_to_google_sheets(sheet_link, topic, chat_link, summary):
    # Replace 'your_credentials.json' with the path to your Google Sheets API credentials file
    print("called google")
    credentials = Credentials.from_service_account_file('your_credential.json', scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive'])
    print(credentials)
    gc = gspread.authorize(credentials)

    # Replace 'Your Spreadsheet Name' with the name of your Google Sheets spreadsheet
    spreadsheet_name = sheet_link
    
    try:
        # Open the Google Sheets spreadsheet
        spreadsheet = gc.open_by_key(spreadsheet_name)

        if spreadsheet is not None:
            print("has access to spreadsheet")
        else:
            print("spreadsheet not found")
        
        # Replace 'Your Worksheet Name' with the name of your worksheet
        worksheet_name = 'Sheet1'

        # Select the worksheet
        worksheet = spreadsheet.worksheet(worksheet_name)

        # Append a new row with the provided data
        new_row = [topic, chat_link, summary]
        worksheet.append_row(new_row)

        print("Data added to Google Sheets successfully.")
    except Exception as e:
        traceback.print_exc()
        print(f"Error adding data to Google Sheets: {str(e)}")


def connect_team_runbook(team_id, google_sheet_link):
    data = request.json
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO gsheetmapping (Team, Sheetlink)
            VALUES (?, ?)
        ''', (team_id, google_sheet_link))
        conn.commit()
        conn.close()
        print("created")
        return "created", 201
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

# Get a specific message by ID
def get_team_runbook(team_id):
    print("team id : ", team_id)
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM gsheetmapping WHERE Team = ?', (team_id,))
        message = cursor.fetchone()
        conn.close()
        print(message)
        if message:
            return message
        else:
            return jsonify({"error": "Message not found"}), 404
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

# Delete a message by ID
def disconnect_team_runbook(team_id):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM gsheetmapping WHERE team = ?', (team_id,))
        conn.commit()
        conn.close()
        print("deleted")
        return "deleted"
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500


# Run the Flask app
if __name__ == "__main__":
    app.run(port=3000, debug=True)

# curl --location 'hackdaylink' \
# --header 'Content-Type: application/json' \
# --header 'Ocp-Apim-Subscription-Key: apikey' \
# --data ' 
# {
#   "displayName": "Conversation Task Example",
#   "analysisInput": {
#     "conversations": [
#       {
#         "conversationItems": [
#           {
#             "text": "Hello, you’re chatting with Rene. How may I help you?",
#             "id": "1",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           },
#           {
#             "text": "Hi, I tried to set up wifi connection for Smart Brew 300 espresso machine, but it didn’t work.",
#             "id": "2",
#             "role": "Customer",
#             "participantId": "Customer_1"
#           },
#           {
#             "text": "I’m sorry to hear that. Let’s see what we can do to fix this issue. Could you please try the following steps for me? First, could you push the wifi connection button, hold for 3 seconds, then let me know if the power light is slowly blinking on and off every second?",
#             "id": "3",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           },
#           {
#             "text": "Yes, I pushed the wifi connection button, and now the power light is slowly blinking.",
#             "id": "4",
#             "role": "Customer",
#             "participantId": "Customer_1"
#           },
#           {
#             "text": "Great. Thank you! Now, please check in your Contoso Coffee app. Does it prompt to ask you to connect with the machine? ",
#             "id": "5",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           },
#           {
#             "text": "No. Nothing happened.",
#             "id": "6",
#             "role": "Customer",
#             "participantId": "Customer_1"
#           },
#           {
#             "text": "I’m very sorry to hear that. Let me see if there’s another way to fix the issue. Please hold on for a minute.",
#             "id": "7",
#             "role": "Agent",
#             "participantId": "Agent_1"
#           }
#         ],
#         "modality": "text",
#         "id": "conversation1",
#         "language": "en"
#       }
#     ]
#   },
#   "tasks": [
#     {
#       "taskName": "Conversation Task 1",
#       "kind": "ConversationalSummarizationTask",
#       "parameters": {
#         "summaryAspects": ["issue"]
#       }
#     },
#     {
#       "taskName": "Conversation Task 2",
#       "kind": "ConversationalSummarizationTask",
#       "parameters": {
#         "summaryAspects": ["resolution"],
#         "sentenceCount": 1
#       }
#     }
#   ]
# }
# '

# def make_post_request(url, headers, params):
#     try:
#         # Make the HTTP POST request
#         response = requests.post(url, headers=headers, params=params)

#         # Print the request details
#         print(f"Request URL: {response.request.url}")
#         print(f"Request Headers: {response.request.headers}")
#         print(f"Request Body: {response.request.body}")

#         # Print the response details
#         print(f"Response Status Code: {response.status_code}")
#         print(f"Response Headers: {response.headers}")
#         print(f"Response Content: {response.text}")

#     except requests.RequestException as e:
#         print(f"Error making HTTP POST request: {e}")

# # Example usage
# url = "https://example.com/api/endpoint"
# auth_headers = {"Authorization": "Bearer YOUR_ACCESS_TOKEN"}
# request_params = {"param1": "value1", "param2": "value2"}

# make_post_request(url, headers=auth_headers, params=request_params)

# #knowledgeCrow create teamId gsheetlink
# #knowledgeCrow get teamId
# #knowledgeCrow delete teamId

# async def async_function():
#     print("Async function started")
#     await asyncio.sleep(2)  # Simulate an asynchronous task (e.g., I/O operation)
#     print("Async function completed")

# asyncio.run(async_function())

