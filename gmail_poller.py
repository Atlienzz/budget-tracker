import os
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service(credentials_file='credentials.json', token_file='token.json'):
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def get_bill_emails(service, query='subject:bill OR subject:payment OR subject:invoice OR subject:due', max_results=10):
    results = service.users().messages().list(
        userId='me',
        q=query,
        maxResults=max_results
    ).execute()

    messages = results.get('messages', [])
    emails = []

    for msg in messages:
        msg_data = service.users().messages().get(
            userId='me',
            id=msg['id'],
            format='full'
        ).execute()

        subject = ''
        date_str = ''
        for header in msg_data['payload']['headers']:
            if header['name'] == 'Subject':
                subject = header['value']
            elif header['name'] == 'Date':
                date_str = header['value']

        from email.utils import parsedate_to_datetime
        try:
            email_date = parsedate_to_datetime(date_str)
        except Exception:
            email_date = None

        body = ''
        if 'parts' in msg_data['payload']:
            for part in msg_data['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
        elif 'body' in msg_data['payload']:
            data = msg_data['payload']['body'].get('data', '')
            body = base64.urlsafe_b64decode(data).decode('utf-8')

        emails.append({
            'id': msg['id'],
            'subject': subject,
            'body': body,
            'date': email_date
        })

    return emails

if __name__ == '__main__':
    try:
        service = get_gmail_service()
        print("✅ Connected to Gmail!")
    
        emails = get_bill_emails(service)
        print(f"Found {len(emails)} emails\n")
    
        for email in emails:
            print(f"Subject: {email['subject']}")
            print(f"Body preview: {email['body'][:200]}")
            print("---")
    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        traceback.print_exc()