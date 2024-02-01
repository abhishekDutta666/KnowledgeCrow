import os
import json
from slack import WebClient
from flask import Flask, request, jsonify
from slackeventsapi import SlackEventAdapter
import sqlite3
import gspread
from google.oauth2.service_account import Credentials

# Initialize Flask app
app = Flask(__name__)

# Database configuration
DATABASE = 'messages'

# Create the table on startup
create_table()

# Initialize Slack WebClient and Event Adapter
slack_token = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=slack_token)
slack_events_adapter = SlackEventAdapter(os.environ["SLACK_SIGNING_SECRET"], "/slack/events", app)

# Define event handler for message events
@slack_events_adapter.on("message")
def message(event_data):
    print(event_data)
    event = event_data["event"]
    if event.get("subtype") is None and "thread_ts" in event:
        channel = event["channel"]
        thread_ts = event["thread_ts"]
        text = event["text"]
        print("passed thread check")
        if "knowledgeCrow" in text:
            print("passed trigger check")
            try:
                # Get conversation history for the thread
                result = client.conversations_replies(channel=channel, ts=thread_ts)
                messages = result["messages"]
                print("passed reply retrieval")
                # Extract user information and message text
                summary = [{"user": message.get("user", ""), "text": message.get("text", "")} for message in messages]
                print("passed summary creation")
                # Prepare JSON response
                response = {
                    "channel_id": channel,
                    "thread_ts": thread_ts,
                    "messages": summary
                }
                add_data_to_google_sheets("Team A", "Topic 1", "https://example.com", "Summary of the chat.")
                print(response)
                return jsonify(response)
            except Exception as e:
                return jsonify({"error": str(e)})

def add_data_to_google_sheets(team, topic, chat_link, summary):
    # Replace 'your_credentials.json' with the path to your Google Sheets API credentials file
    credentials = Credentials.from_service_account_file('your_credentials.json', scopes=['https://www.googleapis.com/auth/spreadsheets'])
    gc = gspread.authorize(credentials)

    # Replace 'Your Spreadsheet Name' with the name of your Google Sheets spreadsheet
    spreadsheet_name = 'Your Spreadsheet Name'
    
    try:
        # Open the Google Sheets spreadsheet
        spreadsheet = gc.open(spreadsheet_name)
        
        # Replace 'Your Worksheet Name' with the name of your worksheet
        worksheet_name = 'Your Worksheet Name'

        # Select the worksheet
        worksheet = spreadsheet.worksheet(worksheet_name)

        # Append a new row with the provided data
        new_row = [team, topic, chat_link, summary]
        worksheet.append_row(new_row)

        print("Data added to Google Sheets successfully.")
    except Exception as e:
        print(f"Error adding data to Google Sheets: {str(e)}")

def create_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS MessageStore (
            Team TEXT,
            Topic TEXT,
            ChatLink TEXT,
            Summary TEXT
        )
    ''')
    conn.commit()
    conn.close()


# Create a new message
@app.route('/messages', methods=['POST'])
def create_message():
    data = request.json
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO MessageStore (Team, Topic, ChatLink, Summary)
            VALUES (?, ?, ?, ?)
        ''', (data['team'], data['topic'], data['chat_link'], data['summary']))
        conn.commit()
        conn.close()
        return jsonify({"message": "Message created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get all messages
@app.route('/messages', methods=['GET'])
def get_messages():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM MessageStore')
        messages = cursor.fetchall()
        conn.close()
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get a specific message by ID
@app.route('/messages/<int:message_id>', methods=['GET'])
def get_message(message_id):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM MessageStore WHERE rowid = ?', (message_id,))
        message = cursor.fetchone()
        conn.close()
        if message:
            return jsonify({"message": message})
        else:
            return jsonify({"error": "Message not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Update a message by ID
@app.route('/messages/<int:message_id>', methods=['PUT'])
def update_message(message_id):
    data = request.json
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE MessageStore
            SET Team = ?, Topic = ?, ChatLink = ?, Summary = ?
            WHERE rowid = ?
        ''', (data['team'], data['topic'], data['chat_link'], data['summary'], message_id))
        conn.commit()
        conn.close()
        return jsonify({"message": "Message updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Delete a message by ID
@app.route('/messages/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM MessageStore WHERE rowid = ?', (message_id,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Message deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#knowledgeCrow create personal gsheetlink
#knowledgeCrow create team teamId gsheetlink
#knowledgeCrow get personal
#knowledgeCrow get team teamId
#knowledgeCrow delete personal
#knowledgeCrow delete team teamId


# Run the Flask app
if __name__ == "__main__":
    app.run(port=3000, debug=True)
