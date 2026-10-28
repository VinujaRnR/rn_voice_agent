import os
from dotenv import load_dotenv
from google import genai


def test_gemini_connection():
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

    if not api_key:
        print("Error: GEMINI_API_KEY is not set in environment or .env file.")
        return

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model,
            contents="Say hello to RN Robots in one sentence."
        )
        print(response.text)
    except Exception as e:
        print(f"Gemini API request failed: {e}")


if __name__ == "__main__":
    test_gemini_connection()
