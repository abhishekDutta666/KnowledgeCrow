import os
from slack_bolt import App

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# Initialize the Slack app with your bot token
app = App(
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    token=os.environ.get("SLACK_BOT_TOKEN"),
)

# Define a command listener for /apollo
@app.command("/apollo")
def apollo_command(ack, say, command):
    # Acknowledge the command request
    ack()

    # Extract information from the command payload
    #channel_id = command["channel_id"]

    # Generate and send the chat link
    #chat_link = f"https://slack.com/app_redirect?channel={channel_id}"
    #say(f"Here is the chat link for the /apollo thread: {chat_link}")
    say(f"Hello")

# Start the app
if __name__ == "__main__":
    app.start(port=int(os.environ.get("PORT", 3000)))
