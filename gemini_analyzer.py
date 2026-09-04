import os
import google.generativeai as genai

# Configure your API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use the recommended model for text analysis
model = genai.GenerativeModel('gemini-1.5-flash')

def analyze_listing(title: str, description: str) -> str:
    prompt = f"""
    You are a strict quality control assistant for a second-hand phone buyer. 
    Analyze the following Facebook Marketplace listing and extract the details into a strict JSON format.

    Listing Title: {title}
    Listing Description: {description}

    CRITICAL FILTERING RULES:
    1. is_scam: Set to true ONLY IF the listing explicitly asks for advance payment, courier delivery only, or mentions "clone", "copy", "first copy", or "fake". Do NOT flag low prices as scams.
    2. is_broken: Set to true if the screen is cracked, back glass is broken, face ID/fingerprint is dead, or there are hardware defects.
    3. is_target_brand: Set to true ONLY if the phone is an Apple iPhone or a Samsung Galaxy. Set to false for Oppo, Vivo, Xiaomi, etc.
    
    You must return a valid JSON object matching this exact schema:
    {{
        "is_scam": boolean,
        "is_broken": boolean,
        "is_target_brand": boolean,
        "battery_health": "string (e.g., '85%', 'Replaced', or 'Unknown')",
        "storage": "string (e.g., '128GB' or 'Unknown')",
        "condition_notes": "string (Brief summary of scratches, warranty, or included accessories)"
    }}
    
    Return ONLY the raw JSON object. Do not include markdown formatting like ```json.
    """
    
    try:
        response = model.generate_content(
            prompt,
            # Forcing JSON output guarantees syntactically correct parsing
            generation_config={"response_mime_type": "application/json"}
        )
        return response.text
    except Exception as e:
        print(f"Gemini generation error: {e}")
        return '{"is_scam": false, "is_broken": false, "is_target_brand": true, "battery_health": "N/A", "storage": "N/A", "condition_notes": "API Error"}'