#!/usr/bin/env python3
"""Test script to validate Gemini API key configuration."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_gemini_api():
    """Test if Gemini API key is valid and working."""
    
    # Check if API key is set
    api_key = os.getenv("GEMINI_API_KEY", "")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    print("=" * 60)
    print("GEMINI API KEY VALIDATION TEST")
    print("=" * 60)
    
    if not api_key:
        print("❌ FAIL: GEMINI_API_KEY is not set in .env file")
        print("\nPlease add your API key to the .env file:")
        print("  GEMINI_API_KEY=your_api_key_here")
        return False
    
    # Mask the key for display
    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    print(f"✓ API Key found: {masked_key}")
    print(f"✓ Model configured: {model_name}")
    
    # Try to import google.generativeai
    try:
        import google.generativeai as genai
        print("✓ google.generativeai package imported successfully")
    except ImportError:
        print("❌ FAIL: google.generativeai package not installed")
        print("  Run: pip install google-generativeai")
        return False
    
    # Configure the API
    try:
        genai.configure(api_key=api_key)
        print("✓ API configured")
    except Exception as e:
        print(f"❌ FAIL: Could not configure API: {e}")
        return False
    
    # Try to list models (basic API test)
    print("\n--- Testing API Connection ---")
    try:
        models = list(genai.list_models())
        print(f"✓ API connection successful! Found {len(models)} models")
        
        # Check if our configured model exists
        model_names = [m.name for m in models]
        if any(model_name in name for name in model_names):
            print(f"✓ Model '{model_name}' is available")
        else:
            print(f"⚠ Warning: Model '{model_name}' not found in available models")
            print("  Available models include:", [n.split('/')[-1] for n in model_names[:5]])
            
    except Exception as e:
        print(f"❌ FAIL: Could not list models: {e}")
        return False
    
    # Try a simple generation
    print("\n--- Testing Content Generation ---")
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Say 'API test successful!' in exactly 3 words.")
        result = response.text.strip()
        print(f"✓ Generation successful!")
        print(f"  Response: {result}")
    except Exception as e:
        print(f"❌ FAIL: Could not generate content: {e}")
        print("\nPossible issues:")
        print("  - Invalid API key")
        print("  - API quota exceeded")
        print("  - Model name incorrect")
        print("  - Network issues")
        return False
    
    # All tests passed
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - Gemini API is working correctly!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_gemini_api()
    sys.exit(0 if success else 1)
