import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from transliteration import transliterate_hinglish_sentence

def test_transliteration():
    inputs = [
        ("Doctor sahab, teen din se fever hai.", "hi_en"),
        ("Mujhe headache ho raha hai.", "hi_en"),
        ("Temperature 102 pe hai. Bohot weakness feel ho rahi hai.", "hi_en"),
        ("Mala chest pain hota aahe.", "mr_en"),
        ("Mane cold ane cough thayo che.", "gu_en"),
        ("Naku chest pain mariyu fever undi.", "te_en")
    ]
    outputs = [transliterate_hinglish_sentence(text, lang) for text, lang in inputs]
    
    print("\n==========================================")
    print("Testing Transliteration:")
    print("==========================================")
    for (orig, lang), res in zip(inputs, outputs):
        print(f"Language: {lang}")
        print(f"Original: {orig}")
        print(f"Result:   {res}\n")
        
    # Hindi checks
    assert "Doctor" in outputs[0]
    assert "fever" in outputs[0]
    assert "मुझे" in outputs[1]
    assert "feel" in outputs[2]
    
    # Marathi checks
    assert "chest" in outputs[3]
    assert "pain" in outputs[3]
    assert "मला" in outputs[3] or "मल" in outputs[3]
    
    # Gujarati checks
    assert "cold" in outputs[4]
    assert "cough" in outputs[4]
    assert "મને" in outputs[4] or "મન" in outputs[4]
    
    # Telugu checks
    assert "chest" in outputs[5]
    assert "pain" in outputs[5]
    assert "నాకు" in outputs[5] or "నాక" in outputs[5]
    
    print("✓ All transliteration assertions passed!")

def test_voice_profiles():
    from tts_engine import get_voice_profile, get_random_voice_profile
    
    # Test that get_voice_profile replaces accents correctly
    p_te = get_voice_profile("doctor", "male", "adult", "te_en")
    print(f"Telugu accent: {p_te}")
    assert "Telugu-English" in p_te
    
    p_mr = get_voice_profile("patient", "female", "adult", "mr_en")
    print(f"Marathi accent: {p_mr}")
    assert "Marathi-English" in p_mr
    
    # Test get_random_voice_profile
    rand_profile = get_random_voice_profile("doctor", "female", "adult", "gu_en")
    print(f"Random Gujarati accent: {rand_profile}")
    assert "Gujarati-English" in rand_profile
    
    print("✓ All voice profile assertions passed!")

if __name__ == "__main__":
    test_transliteration()
    test_voice_profiles()
