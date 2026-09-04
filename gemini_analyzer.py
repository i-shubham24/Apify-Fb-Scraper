import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-3.5-flash')

def analyze_listing(title: str, description: str, listing_price: float) -> str:
    prompt = f"""
    You are an expert second-hand electronics pricing analyst in Canada. 
    Analyze the following Facebook Marketplace listing and extract details into a strict JSON format.

    Listing Title: {title}
    Listing Description: {description}
    Listed Price: ${listing_price} CAD

    RULES:
    1. is_scam: Set to true if it requires advance payment, shipping-only, or mentions clone/fake/replica.
    2. is_broken: Set to true if screen/body is cracked or hardware is defective.
    3. is_target_brand: Set to true ONLY for Apple iPhone or Samsung Galaxy.
    4. estimated_market_value: Estimate the average used market price in CAD for this specific model and storage configuration in Canada (numeric value only).
    5. deal_score: Rate the deal from 1 to 10 based on how much lower the listed price is compared to the estimated market value (10 = massive steal/underpriced, 1 = overpriced).
    
    Return a valid JSON object matching this exact schema:
    {{
        "is_scam": boolean,
        "is_broken": boolean,
        "is_target_brand": boolean,
        "battery_health": "string (e.g., '85%' or 'Unknown')",
        "storage": "string (e.g., '128GB' or 'Unknown')",
        "estimated_market_value": number,
        "deal_score": integer,
        "condition_notes": "string"
    }}
    
    Return ONLY raw JSON without markdown formatting.
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return response.text
    except Exception as e:
        print(f"Gemini generation error: {e}")
        return '{"is_scam": false, "is_broken": false, "is_target_brand": true, "battery_health": "N/A", "storage": "N/A", "estimated_market_value": 0, "deal_score": 5, "condition_notes": "API Error"}'