import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class PhoneAnalysis(BaseModel):
    battery_health: str = Field(description="Battery health percentage, or 'Unknown'")
    storage: str = Field(description="Storage size (e.g., 128GB), or 'Unknown'")
    condition_notes: str = Field(description="Any mentions of cracks, scratches, or locks. Brief.")
    is_scam: bool = Field(description="True if it looks fake, just selling a case, or suspicious")

def analyze_listing(title: str, description: str):
    prompt = f"Analyze this Facebook Marketplace listing:\nTitle: {title}\nDescription: {description}"
    
    # gemini-2.5-flash is extremely fast and free
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PhoneAnalysis,
            temperature=0.1,
        ),
    )
    
    # Returns a validated JSON string
    return response.text