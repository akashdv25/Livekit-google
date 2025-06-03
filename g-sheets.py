import os.path
import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]  # Full access to Sheets w-r-d

# The ID and range of a sample spreadsheet.
SAMPLE_SPREADSHEET_ID = "1QBTDOqKoPFuHFMordHVgNRt3S20zVnQgPigzk1kIzdQ"
SAMPLE_RANGE_NAME = "Sheet1!A1:D3"

# access the credentials.json file to get the credentials
def get_credentials():
    """Gets valid user credentials from storage.
    
    Returns:
        Credentials, the obtained credential.
    """
    creds = None
    
    # if the credentials file exists, use it
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # if the credentials are not valid, refresh the credentials
    if not creds or not creds.valid:
        
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
                
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            
            creds = flow.run_local_server(port=0)
        
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    return creds


def read_sheet(sheet, spreadsheet_id, range_name):
    """Reads data from a Google Sheet.
    
    Args:
        sheet: Google Sheets API service instance
        spreadsheet_id: ID of the spreadsheet
        range_name: Range to read from (e.g., "Sheet1!A1:C3")
    
    Returns:
        List of rows containing the values
    """
    try:
        result = (
            sheet.values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )

        values = result.get("values", [])
        
        if not values:
            print("No data found.")
            return []
        
        return values
    
    except HttpError as err:
        print(f"Error reading sheet: {err}")
        return []

def update_sheet(sheet, spreadsheet_id, range_name, values):
    """Updates data in a Google Sheet.
    
    Args:
        sheet: Google Sheets API service instance
        spreadsheet_id: ID of the spreadsheet
        range_name: Range to update (e.g., "Sheet1!A2")
        values: 2D array of values to update with
    
    Returns:
        Number of cells updated
    """
    try:
        request = sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": values}
        ).execute()

        return request.get("updatedCells")
    
    except HttpError as err:
        print(f"Error updating sheet: {err}")
        return 0

def delete_rows(sheet, spreadsheet_id, range_name):
    """Clears data from specified range in a Google Sheet.
    
    Args:
        sheet: Google Sheets API service instance
        spreadsheet_id: ID of the spreadsheet
        range_name: Range to clear (e.g., "Sheet1!A2:C2")
    
    Returns:
        Range that was cleared
    """
    try:
        request = sheet.values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        return request.get("clearedRange")
    except HttpError as err:
        print(f"Error deleting data: {err}")
        return None


def main():
    """Example usage of the Sheets API functions."""
    try:
        # Get credentials and build service
        creds = get_credentials()
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Example 1: Read data
        print("Reading current data:")
        values = read_sheet(sheet, SAMPLE_SPREADSHEET_ID, SAMPLE_RANGE_NAME)
        for row in values:
            print(f"{row[0]}, {row[2]}")

        # Example 2: Update data
        print("\nUpdating a record:")
        update_range = "Sheet1!B2"
        update_values = [["Updated address: maggarpatta, Pune, Maharashtra, India"]]
        cells_updated = update_sheet(sheet, SAMPLE_SPREADSHEET_ID, update_range, update_values)
        print(f"Updated {cells_updated} cells")

        # Example 3: Delete data (clear cells)
        print("\nDeleting data from range:")
        delete_range = "Sheet1!D2:D3"  # Example: clear column D
        cleared_range = delete_rows(sheet, SAMPLE_SPREADSHEET_ID, delete_range)
        if cleared_range:
            print(f"Cleared range: {cleared_range}")

        # Read again to show changes
        print("\nReading updated data:")
        values = read_sheet(sheet, SAMPLE_SPREADSHEET_ID, SAMPLE_RANGE_NAME)
        for row in values:
            print(f"{row[0]}, {row[2]}")

    except HttpError as err:
        print(err)

if __name__ == "__main__":
    main()