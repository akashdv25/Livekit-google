import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import asyncio
import json
from livekit import api
import logging

# Set up logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Print environment variables (without secrets)
logger.info("Checking environment variables...")
logger.info(f"LIVEKIT_URL set: {bool(os.getenv('LIVEKIT_URL'))}")
logger.info(f"API_KEY set: {bool(os.getenv('LIVEKIT_API_KEY'))}")
logger.info(f"API_SECRET set: {bool(os.getenv('LIVEKIT_API_SECRET'))}")
logger.info(f"SIP_OUTBOUND_TRUNK_ID set: {bool(os.getenv('SIP_OUTBOUND_TRUNK_ID'))}")

SPREADSHEET_ID = "1QBTDOqKoPFuHFMordHVgNRt3S20zVnQgPigzk1kIzdQ"
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
API_KEY = os.getenv("LIVEKIT_API_KEY")
API_SECRET = os.getenv("LIVEKIT_API_SECRET")

def format_phone_number(number: str) -> str:
    """Format phone number to E.164 format"""
    # Remove any spaces, dashes, or other characters
    cleaned = ''.join(filter(str.isdigit, str(number)))
    
    # Handle empty or invalid numbers
    if not cleaned:
        raise ValueError("Phone number cannot be empty")
        
    # Remove leading zeros
    cleaned = cleaned.lstrip('0')
    
    # If number starts with country code (91), use it
    if cleaned.startswith('91') and len(cleaned) > 10:
        base_number = cleaned
    # If it's a 10-digit number, add country code
    elif len(cleaned) == 10:
        base_number = '91' + cleaned
    else:
        raise ValueError(f"Invalid phone number format: {number}. Must be 10 digits or include 91 prefix.")
    
    # Add the + prefix
    return f"+{base_number}"

def get_sheets_service():
    """Gets Google Sheets service instance"""
    try:
        creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/spreadsheets"])
        service = build("sheets", "v4", credentials=creds)
        return service.spreadsheets()
    except Exception as e:
        logger.error(f"Error getting sheets service: {e}")
        return None

async def dispatch_call(lk_api: api.LiveKitAPI, customer: dict):
    """Dispatch a single call using LiveKit's recommended method"""
    try:
        logger.info(f"Starting dispatch for customer: {customer}")
        
        # Format the phone number
        formatted_number = format_phone_number(customer['number'])
        logger.info(f"Formatted phone number: {formatted_number}")
        
        # Create a unique room name
        room_name = f"call_{formatted_number}_{int(asyncio.get_event_loop().time())}"
        logger.info(f"Created room name: {room_name}")

        # Prepare metadata for the agent
        metadata = json.dumps({
            "phone_number": formatted_number,
            "customer_data": customer
        })
        logger.info("Prepared metadata for agent")

        # Create agent dispatch first
        logger.info("Creating agent dispatch...")
        try:
            dispatch = await lk_api.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="outbound-caller",
                    room=room_name,
                    metadata=metadata
                )
            )
            logger.info(f"Successfully created agent dispatch: {dispatch}")
        except Exception as e:
            logger.error(f"Failed to create agent dispatch: {e}")
            return False

        # Wait briefly for dispatch to be ready
        await asyncio.sleep(1)

        # Get SIP trunk ID from environment
        sip_trunk_id = os.getenv('SIP_OUTBOUND_TRUNK_ID')
        if not sip_trunk_id:
            logger.error("SIP_OUTBOUND_TRUNK_ID not found in environment")
            raise ValueError("SIP_OUTBOUND_TRUNK_ID not found in environment")

        # Create SIP participant to initiate the call
        logger.info(f"Creating SIP participant with trunk ID: {sip_trunk_id}")
        try:
            participant = await lk_api.sip.create_sip_participant(api.CreateSIPParticipantRequest(
                room_name=room_name,
                sip_trunk_id=sip_trunk_id,
                sip_call_to=formatted_number,
                participant_identity=formatted_number,
                wait_until_answered=True
            ))
            logger.info(f"Successfully created SIP participant: {participant}")
        except Exception as e:
            logger.error(f"Failed to create SIP participant: {e}")
            return False

        logger.info(f"Successfully dispatched call to {formatted_number}")
        return True

    except Exception as e:
        logger.error(f"Error dispatching call to {customer.get('number')}: {str(e)}")
        return False

async def dispatch_calls():
    """Main function to dispatch calls"""
    try:
        # Get sheets service
        logger.info("Getting Google Sheets service...")
        sheet = get_sheets_service()
        if not sheet:
            logger.error("Could not access Google Sheets")
            return

        # Read customer data
        logger.info(f"Reading customer data from sheet ID: {SPREADSHEET_ID}")
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="Sheet1!A2:D"  # Assuming data starts from row 2
        ).execute()
        
        values = result.get("values", [])
        if not values:
            logger.info("No customer data found in sheet")
            return
        
        logger.info(f"Found {len(values)} customers in sheet")

        # Create LiveKit API instance
        logger.info("Creating LiveKit API instance...")
        lk_api = api.LiveKitAPI()

        try:
            # Process customers one by one
            for row in values:
                if len(row) >= 4:  # Ensure row has all required fields
                    customer = {
                        "index": row[0],
                        "name": row[1],
                        "number": row[2],
                        "address": row[3]
                    }

                    logger.info(f"Processing customer: {customer}")
                    
                    # Dispatch the call
                    success = await dispatch_call(lk_api, customer)
                    
                    if success:
                        # Wait between calls (60 seconds)
                        logger.info("Call successful. Waiting 60 seconds before next call...")
                        await asyncio.sleep(60)
                    else:
                        logger.warning(f"Call failed for customer {customer['name']}. Skipping to next customer...")
                        await asyncio.sleep(5)  # Short delay before next attempt
                else:
                    logger.warning(f"Skipping row due to missing fields: {row}")

        finally:
            # Properly close the API client
            logger.info("Closing LiveKit API client...")
            await lk_api.aclose()

    except Exception as e:
        logger.error(f"Error in dispatch_calls: {str(e)}")

if __name__ == "__main__":
    logger.info("Starting dispatch script...")
    asyncio.run(dispatch_calls()) 