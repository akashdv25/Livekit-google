# LiveKit Outbound Calling System with Google Sheets Integration

This application implements an automated outbound calling system using LiveKit that reads customer data from Google Sheets, makes calls, and updates customer information through voice conversations.

## System Overview

The system consists of two main components:

1. **Dispatch System** (`dispatch_calls.py`)
   - Reads customer data from Google Sheets
   - Creates rooms for each call
   - Manages SIP participant creation
   - Handles outbound calling process

2. **Conversation Agent** (`agent.py`)
   - Manages the conversation flow
   - Verifies and updates customer details
   - Handles call lifecycle
   - Updates Google Sheets when information changes

## Prerequisites

- Python 3.8+
- LiveKit account and credentials
- Google Cloud project with Sheets API enabled
- SIP trunk configuration in LiveKit

## Environment Variables

Create a `.env` file with the following variables:
```
LIVEKIT_URL=your_livekit_url
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
SIP_OUTBOUND_TRUNK_ID=your_trunk_id
```

## Google Sheets Setup

1. Create a Google Sheet with the following columns:
   - Column A: Index (0-based)
   - Column B: Name
   - Column C: Phone Number
   - Column D: Address

2. Get the Sheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit
   ```

3. Update `SPREADSHEET_ID` in both `dispatch_calls.py` and `agent.py`

## Google Sheets Authentication

The `g-sheets.py` script handles Google Sheets authentication:

1. First-time setup:
   ```bash
   python g-sheets.py
   ```
   This will:
   - Open a browser window for Google authentication
   - Create a `token.json` file with credentials
   - Test the connection to your sheet

2. The `token.json` file will be used by both `dispatch_calls.py` and `agent.py` for sheet access

## Application Flow

1. **Dispatch Process** (`dispatch_calls.py`):
   ```
   Read Sheet Data → Create Room → Create Agent → Make Outbound Call
   ```
   - Reads customer data row by row
   - Creates a unique room for each call
   - Dispatches an agent to the room
   - Initiates outbound call via SIP
   - Waits 60 seconds between calls

2. **Conversation Flow** (`agent.py`):
   ```
   Connect → Verify Details → Update if Needed → End Call
   ```
   - Greets customer and verifies details
   - Updates Google Sheets if information is incorrect
   - Confirms updates with customer
   - Ends call appropriately

3. **Data Updates**:
   - When customer provides new information:
     ```
     Receive Update → Update Sheet → Confirm Change → Verify
     ```
   - Updates are logged in `call_log.csv`

## Running the Application

1. Start the dispatch system:
   ```bash
   python dispatch_calls.py
   ```

2. The agent will automatically handle each call as they're dispatched

## Logging

The system maintains two types of logs:

1. **Application Logs**: Detailed system logs with DEBUG level information

2. **Call Logs** (`call_log.csv`):
   - Timestamp
   - Event Type
   - Speaker
   - Text/Action



## Phone Number Formatting

Phone numbers are automatically formatted to E.164 format:
- Accepts 10-digit numbers or numbers with '91' prefix
- Automatically adds '+91' prefix if needed
- Validates number format before making calls

## Best Practices

1. Always maintain proper Google Sheets credentials
2. Monitor `call_log.csv` for conversation tracking
3. Keep environment variables secure
4. Regularly check LiveKit dashboard for call status
5. Maintain good internet connectivity for stable calls

## Troubleshooting

Common issues and solutions:

1. **Sheet Access Issues**:
   - Verify `token.json` exists and is valid
   - Check sheet permissions
   - Run `g-sheets.py` to refresh credentials

2. **Call Failures**:
   - Check SIP trunk configuration
   - Verify phone number format
   - Check LiveKit logs for detailed errors

3. **Update Failures**:
   - Verify sheet permissions include write access
   - Check column mappings
   - Review error logs for specific issues 