import re
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

# Common English clinical words to preserve (should not be transliterated)
ENGLISH_CLINICAL_WORDS = {
    "doctor", "dr", "patient", "pt", "nurse", "attendant", "receptionist", "relative", 
    "headache", "fever", "cough", "cold", "pain", "chest", "heart", "stomach", "vomiting", 
    "weakness", "temperature", "bp", "blood", "pressure", "sugar", "diabetes", "insulin", 
    "tablet", "capsule", "medicine", "syrup", "injection", "test", "report", "urine", 
    "scan", "xray", "hospital", "opd", "clinic", "appointment", "checkup", "days", "months", 
    "years", "age", "weight", "height", "problem", "symptom", "feverish", "headache", "migraine"
}

# Standard English grammatical words to preserve
COMMON_ENGLISH_WORDS = {
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "mine", "yours", "ours", "theirs",
    "and", "but", "or", "so", "because", "if", "then", "else", "when", "where", "why",
    "how", "what", "which", "who", "whom", "whose", "this", "that", "these", "those",
    "a", "an", "the", "in", "on", "at", "to", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "from",
    "up", "down", "off", "over", "under", "again", "further",
    "once", "here", "there", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "than", "too", "very",
    "can", "will", "just", "should", "now", "yes", "ok", "okay", "hi", "hello", "please",
    "thank", "thanks", "welcome", "good", "morning", "afternoon", "evening", "night",
    "day", "week", "month", "year", "yesterday", "today", "tomorrow", "time", "date",
    "hour", "minute", "second", "one", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "hundred", "thousand", "first", "second", "third", "last",
    "feel", "feels", "feeling", "is", "are", "am", "was", "were", "be", "been", "have", 
    "has", "had", "do", "does", "did", "say", "said", "go", "went", "gone", "take", 
    "took", "taken", "come", "came", "give", "gave", "given", "see", "saw", "seen", 
    "know", "knew", "known", "make", "made", "like", "liked", "want", "wanted", "think", 
    "thought", "look", "looked", "get", "got", "gotten", "find", "found", "work", 
    "worked", "tell", "told", "ask", "asked", "use", "used", "need", "needed", "write", 
    "wrote", "written", "read", "prescribe", "visit", "consult", "advise", "recommend",
    "history", "admit", "discharge", "dose", "tablet", "capsules", "injections"
}

ALL_ENGLISH_WORDS = ENGLISH_CLINICAL_WORDS.union(COMMON_ENGLISH_WORDS)

# Predefined dictionary for very common Hinglish particles and pronouns to guarantee correctness
HINGLISH_DIRECT_MAP = {
    "mujhe": "मुझे",
    "aap": "आप",
    "tum": "तुम",
    "mera": "मेरा",
    "meri": "मेरी",
    "mere": "मेरे",
    "ko": "को",
    "se": "से",
    "ka": "का",
    "ki": "की",
    "ke": "के",
    "ne": "ने",
    "ho": "हो",
    "hai": "है",
    "hain": "हैं",
    "tha": "था",
    "thi": "थी",
    "the": "थे",
    "raha": "रहा",
    "rahi": "रही",
    "rahe": "रहे",
    "kya": "क्या",
    "kyon": "क्यों",
    "kyu": "क्यों",
    "kuch": "कुछ",
    "bohot": "बहुत",
    "bahut": "बहुत",
    "hoga": "होगा",
    "hogi": "होगी",
    "hoge": "होंगे",
    "aur": "और",
    "bhi": "भी",
    "ab": "अब",
    "tab": "तब",
    "kab": "कब",
    "sab": "सब",
    "par": "पर",
    "na": "ना",
    "nahi": "नहीं",
    "nahin": "नहीं",
    "naam": "नाम",
    "beta": "बेटा",
    "beti": "बेटी",
    "bachcha": "बच्चा",
    "bachha": "बच्चा",
    "kal": "कल",
    "aaj": "आज",
    "raat": "रात",
    "subah": "सुबह",
    "dopahar": "दोपहर",
    "shaam": "शाम",
    "ek": "एक",
    "do": "दो",
    "teen": "तीन",
    "char": "चार",
    "paanch": "पाँच",
    "chhah": "छह",
    "saat": "सात",
    "aath": "आठ",
    "nau": "नौ",
    "das": "दस",
    "dawa": "दवा",
    "ji": "जी",
    "betaa": "बेटा",
    "arjun": "अर्जुन",
    "aiye": "आइए",
    "aaiye": "आइए",
    "aao": "आओ",
    "baithiye": "बैठिए",
    "baitho": "बैठो",
    "dikhaaiye": "दिखाइए",
    "dikhao": "दिखाओ",
    "kijiye": "कीजिए",
    "karo": "करो",
    "boliay": "बोलिए",
    "boliye": "बोलिए",
    "sunye": "सुनिए",
    "suniye": "सुनिए",
    "likh": "लिख",
    "de": "दे",
    "diya": "दिया",
    "le": "ले",
    "lo": "लो",
    # Marathi additions
    "mala": "मला",
    "aahe": "आहे",
    "hota": "होता",
    "thoda": "थोडा",
    # Gujarati additions
    "mane": "મને",
    "che": "છે",
    "ane": "અને",
    "thayo": "થયો",
    "doktar": "ડોક્ટર",
    # Telugu additions
    "naku": "నాకు",
    "undi": "ఉంది",
    "mariyu": "మరియు",
    "avunu": "అవును"
}

def transliterate_word(word: str, lang: str = "hi") -> str:
    word_lower = word.lower().strip()
    if not word_lower:
        return word
    
    # If the word does not contain English letters, it is already in a native script or numeric/symbolic. Leave it as-is.
    if not re.search(r'[a-zA-Z]', word):
        return word

    # Preserve non-alphabetic characters (numbers, symbols, punctuation)
    if not word_lower.isalpha():
        return word
    
    # 1. Check direct Hinglish mapping list first (highest accuracy for regional grammar)
    if lang in ('hi', 'mr', 'hi_en', 'mr_en', 'gu', 'gu_en', 'te', 'te_en') and word_lower in HINGLISH_DIRECT_MAP:
        return HINGLISH_DIRECT_MAP[word_lower]
        
    # 2. Check if it's a preserved English word
    if word_lower in ALL_ENGLISH_WORDS:
        return word
        
    # 3. Transliterate using indic-transliteration
    itrans_word = word_lower
    # Map common Roman spelling shortcuts to ITRANS equivalents
    itrans_word = re.sub(r'oo', 'u', itrans_word)
    itrans_word = re.sub(r'ee', 'i', itrans_word)
    itrans_word = re.sub(r'aa', 'A', itrans_word)
    itrans_word = re.sub(r'sh', 'sh', itrans_word)
    itrans_word = re.sub(r'ch', 'ch', itrans_word)
    itrans_word = re.sub(r'kh', 'kh', itrans_word)
    itrans_word = re.sub(r'gh', 'gh', itrans_word)
    itrans_word = re.sub(r'jh', 'jh', itrans_word)
    itrans_word = re.sub(r'bh', 'bh', itrans_word)
    itrans_word = re.sub(r'dh', 'dh', itrans_word)
    itrans_word = re.sub(r'th', 'th', itrans_word)
    itrans_word = re.sub(r'ph', 'ph', itrans_word)
    
    # Select script target based on language
    target_script = sanscript.DEVANAGARI
    if lang in ('gu', 'gu_en'):
        target_script = sanscript.GUJARATI
    elif lang in ('te', 'te_en'):
        target_script = sanscript.TELUGU

    devanagari_word = transliterate(itrans_word, sanscript.ITRANS, target_script)
    return devanagari_word

def transliterate_hinglish_sentence(text: str, lang: str = "hi") -> str:
    """
    Split sentence into words/tokens, transliterate Romanized Hindi/Hinglish/regional words
    while preserving punctuation and English clinical words.
    """
    if not text:
        return ""
    # Split by spaces and punctuation, capturing splits so we can reconstruct the sentence
    tokens = re.split(r'(\s+|[.,!?;:\(\)\[\]"\'`\-\/])', text)
    result = []
    for token in tokens:
        if not token.strip() or not token[0].isalpha():
            result.append(token)
        else:
            result.append(transliterate_word(token, lang))
    return "".join(result)
