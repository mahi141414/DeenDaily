import json
import os
import pickle
import sys

from google.oauth2.credentials import Credentials


def main():
    token_path = sys.argv[1] if len(sys.argv) > 1 else "token.pickle"
    if not os.path.exists(token_path):
        print(f"Token file not found: {token_path}")
        sys.exit(1)

    with open(token_path, "rb") as token_file:
        creds = pickle.load(token_file)

    if not isinstance(creds, Credentials):
        print("Loaded token is not a google.oauth2.credentials.Credentials object.")
        sys.exit(1)

    print(creds.to_json())


if __name__ == "__main__":
    main()
