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

DATABASE = 'knowledge-crow'
app = Flask(__name__)
# Initialize Slack WebClient and Event Adapter
slack_token = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=slack_token)
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
                summary = [{"user": message.get("user", ""), "text": message.get("text", "")} for message in messages]
                response = {
                    "channel_id": channel,
                    "thread_ts": thread_ts,
                    "messages": summary,
                    "ok":"true"
                }
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
                _, status = add_data_to_google_sheets(sheet_key, title, chat_link, "summary")
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
        new_row = [topic, chat_link, summary]
        worksheet.append_row(new_row)

        print("Data added to Google Sheets successfully.")
        return "ok", 200
    except Exception as e:
        print(f"Error adding data to Google Sheets: {str(e)}")
        return "failure", 500


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

