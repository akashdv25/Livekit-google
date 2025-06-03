from dotenv import load_dotenv
import os
from livekit.agents import BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip
from livekit import agents, rtc, api
from livekit.agents import Agent, RoomInputOptions, AgentSession  # <-- this line is key
from livekit.plugins.turn_detector.english import EnglishModel
from livekit.plugins import deepgram
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
from livekit.agents import get_job_context
import json
import asyncio
import logging
import csv
import datetime
import atexit
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# -------- CSV Logging Setup --------

csv_file = open('call_log.csv', mode='a', newline='', encoding='utf-8')
csv_writer = csv.writer(csv_file)

# Write header if file is empty
if os.stat('call_log.csv').st_size == 0:
    csv_writer.writerow(['timestamp', 'event_type', 'speaker', 'text'])

def log_event(event_type, speaker, text):
    timestamp = datetime.datetime.now().isoformat()
    csv_writer.writerow([timestamp, event_type, speaker, text])
    csv_file.flush()  # write immediately

atexit.register(csv_file.close)

# -------- End CSV Logging Setup --------


# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

# -------- Google Sheets Setup --------
SPREADSHEET_ID = "1QBTDOqKoPFuHFMordHVgNRt3S20zVnQgPigzk1kIzdQ"

def get_sheets_service():
    """Gets Google Sheets service instance"""
    try:
        creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/spreadsheets"])
        service = build("sheets", "v4", credentials=creds)
        return service.spreadsheets()
    except Exception as e:
        logger.error(f"Error getting sheets service: {e}")
        return None

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
            You are a professional call agent. Your task is to:
            1. Confirm the customer details I provide
            2. If the user says ANY information is incorrect:
               - Ask them for the correct information
               - Use the update_customer_details function to update it
               - Confirm the update was successful
               - Read back the updated information to verify
            3. Be polite and professional
            4. Keep responses brief and to the point
            5. End the call if the user requests
            6. Detect and handle voicemail systems appropriately
            7. If the user says anything like "goodbye", "hang up", "bye", or "end the call", you MUST call the `end_call` function tool.
            
            When updating details:
            - For name updates, use field="name"
            - For address updates, use field="address"
            - Always confirm the update was successful before proceeding
            """
        )

    @agents.function_tool
    async def update_customer_details(self, ctx: agents.RunContext, field: str, value: str):
        """Update customer details in Google Sheets. Use field='name' or field='address'."""
        try:
            # Get customer data from session
            customer_data = getattr(ctx.session, 'customer_data', None)
            logger.info(f"Retrieved customer data from session: {customer_data}")
            
            if not customer_data:
                error_msg = "No customer data found in session"
                logger.error(error_msg)
                return {"error": error_msg}

            if 'index' not in customer_data:
                error_msg = "No row index found in customer data"
                logger.error(error_msg)
                return {"error": error_msg}

            row_number = int(customer_data['index']) + 1  # Add 1 because sheet is 1-indexed
            logger.info(f"Updating row {row_number}, field {field} to value {value}")

            # Map fields to columns
            column_mapping = {
                "name": "B",
                "address": "D"
            }
            
            if field not in column_mapping:
                error_msg = f"Invalid field: {field}. Must be 'name' or 'address'"
                logger.error(error_msg)
                return {"error": error_msg}

            range_name = f"Sheet1!{column_mapping[field]}{row_number}"
            logger.info(f"Updating range: {range_name}")

            try:
                # Get sheets service
                sheets = get_sheets_service()
                if not sheets:
                    error_msg = "Failed to initialize Google Sheets service"
                    logger.error(error_msg)
                    return {"error": error_msg}

                result = sheets.values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body={"values": [[value]]}
                ).execute()
                
                logger.info(f"Update result: {result}")
                log_event('sheet_update', 'agent', f"Updated {field} to {value} in row {row_number}")
                
                # Update the session's customer data
                if field == "name":
                    customer_data['name'] = value
                elif field == "address":
                    customer_data['address'] = value
                ctx.session.customer_data = customer_data
                logger.info(f"Updated session customer data: {customer_data}")
                
                return {
                    "status": "success", 
                    "message": f"Updated {field} to: {value}",
                    "updated_cells": result.get('updatedCells', 0)
                }

            except Exception as e:
                error_msg = f"Error during sheets update: {str(e)}"
                logger.error(error_msg)
                return {"error": error_msg}

        except Exception as e:
            error_msg = f"Error in update_customer_details: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    @agents.function_tool
    async def end_call(self, ctx: agents.RunContext):
        logger.info("🔔 end_call function_tool triggered")
        log_event('function_call', 'agent', 'end_call triggered')

        """Called when the user wants to end the call"""
        # let the agent finish speaking
        current_speech = ctx.session.current_speech
        if current_speech:
            await current_speech.wait_for_playout()
        await self.hangup_call(ctx)

    @agents.function_tool
    async def detected_answering_machine(self, ctx: agents.RunContext):
        """Call this tool if you have detected a voicemail system, AFTER hearing the voicemail greeting"""
        logger.info("Detected answering machine")
        log_event('event', 'agent', 'Detected answering machine')

        await ctx.session.generate_reply(
            instructions="Leave a voicemail message letting the user know you'll call back later."
        )
        await asyncio.sleep(0.5)  # Add a natural gap to the end of the voicemail message
        await self.hangup_call(ctx)

    async def hangup_call(self, ctx: agents.RunContext):
        """Utility method to hang up the call"""
        try:
            job_ctx = get_job_context()  # This should get the JobContext from RunContext
            log_event('event', 'agent', f'Hanging up call, deleting room {job_ctx.room.name}')
            await job_ctx.api.room.delete_room(
                api.DeleteRoomRequest(
                    room=job_ctx.room.name,
                )
            )
        except Exception as e:
            logger.error(f"Error hanging up call: {e}")
            log_event('error', 'agent', f"Error hanging up call: {e}")

    # async def on_user_speech(self, ctx: agents.RunContext, text: str):
    #     # This method is illustrative — if you have a hook for user speech events,
    #     # log what the user said:
    #     log_event('user_speech', 'user', text)

    # async def on_agent_reply(self, ctx: agents.RunContext, text: str):
    #     # Similarly, log agent replies if you can hook here
    #     log_event('agent_reply', 'agent', text)


async def entrypoint(ctx: agents.JobContext):
    logger.info("Starting agent session")
    log_event('event', 'system', 'Starting agent session')

    # Log metadata before parsing
    logger.info(f"Raw job metadata: {ctx.job.metadata}")
    
    customer_data = None
    try:
        if ctx.job.metadata:
            metadata = json.loads(ctx.job.metadata)
            customer_data = metadata.get("customer_data", {})
            logger.info(f"Parsed customer data: {customer_data}")
        else:
            logger.warning("No metadata provided in job context")
    except Exception as e:
        logger.error(f"Error parsing metadata: {e}")

    await ctx.connect()
    
    # Create the agent instance
    agent = Assistant()

    # Create and start the session
    session = AgentSession(
        turn_detection=EnglishModel(),
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=openai.LLM(model="gpt-4o"),
        tts=cartesia.TTS(),
        vad=silero.VAD.load(),
        min_interruption_duration=0.5,
    )

    # Start the session
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
        ],
    )

    await background_audio.start(room=ctx.room, agent_session=session)

    try:
        if customer_data:
            # Store customer data in session for later use
            session.customer_data = customer_data
            logger.info(f"Stored customer data in session: {customer_data}")
            
            # This is an outbound call with customer data
            await session.generate_reply(
                instructions=f"""
                Greet the person warmly, introduce yourself as an AI assistant.
                Say you're calling to confirm their details.
                According to the records:
                - Their name is: {customer_data.get('name', 'not found')}
                - Their address is: {customer_data.get('address', 'not found')}
                Ask them if these details are correct.
                If they say any detail is incorrect, use the update_customer_details function to update it.
                Keep it brief and professional.
                """
            )
            log_event('agent_reply', 'agent', "Initial greeting sent for outbound call")
        else:
            logger.warning("No customer data found in metadata")
            await session.generate_reply(
                instructions="Greet the user warmly, introduce yourself as an AI assistant, and ask for their name and phone number to look up their details."
            )
    except Exception as e:
        logger.error(f"Error handling call: {e}")
        log_event('error', 'system', f"Error handling call: {e}")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="outbound-caller",
    ))
