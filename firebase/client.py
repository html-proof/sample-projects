import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv

load_dotenv()

def init_firebase():
    """Initializes the Firebase Admin SDK using service account credentials."""
    if not firebase_admin._apps:
        cred_json = os.getenv("FIREBASE_CREDENTIALS")
        db_url = os.getenv("FIREBASE_DATABASE_URL")
        
        if not cred_json:
            print("WARNING: FIREBASE_CREDENTIALS not found in environment. Using default credentials.")
            # Fallback for local development if BYPASS_AUTH is true
            if os.getenv("BYPASS_AUTH", "false").lower() == "true":
                firebase_admin.initialize_app(options={'databaseURL': db_url})
            else:
                raise ValueError("FIREBASE_CREDENTIALS is required unless BYPASS_AUTH is true.")
        else:
            try:
                # Load JSON from string
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': db_url
                })
                print("Firebase initialized successfully.")
            except Exception as e:
                print(f"Error initializing Firebase: {e}")
                raise e

def verify_token(id_token: str):
    """Verifies a Firebase ID token."""
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None
