
import getpass

from werkzeug.security import generate_password_hash
from database import get_connection, initialize_database


def create_authority():
    initialize_database()

    print("\n=== CITINOVA AI | AUTHORITY ACCOUNT SETUP ===")

    name = input("Enter authority name: ").strip()
    email = input("Enter authority email: ").strip().lower()
    password = getpass.getpass("Create password (minimum 8 characters): ")
    confirm_password = getpass.getpass("Confirm password: ")

    if not name or not email or not password:
        print("Error: All fields are required.")
        return

    if len(password) < 8:
        print("Error: Password must contain at least 8 characters.")
        return

    if password != confirm_password:
        print("Error: Passwords do not match.")
        return

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, 'authority')
            """,
            (name, email, generate_password_hash(password))
        )

        connection.commit()
        print("\nAuthority account created successfully!")

    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            print("An account with this email already exists.")
        else:
            print("Could not create account:", error)

    finally:
        connection.close()


if __name__ == "__main__":
    create_authority()
