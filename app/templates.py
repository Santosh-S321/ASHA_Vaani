"""Every sentence the agent speaks. The LLM never writes what she hears.

Native speakers should review these lines before the demo.
"""
from datetime import date

T = {
    "hi": {
        "greet": "नमस्ते। मैं एक AI सहायक हूँ, इंसान नहीं। मैं आपकी विज़िट का रिकॉर्ड भरने में मदद करूँगी। लाभार्थी का ID या नाम बताइए।",
        "found": "{name}, ID {id}, {btype}। अब विज़िट की जानकारी बोलिए।",
        "not_found": "यह लाभार्थी नहीं मिला। ID एक-एक अंक करके फिर से बताइए।",
        "ask_weight_kg": "वज़न कितना है?",
        "ask_visit_type": "यह कौन सी विज़िट है: ANC जांच, नवजात विज़िट, या टीकाकरण?",
        "weight_check": "वज़न {w} किलो सही नहीं लग रहा। कृपया वज़न फिर से बताइए।",
        "readback": "मैं पढ़कर सुनाती हूँ। ID {id}। विज़िट: {visit_type}। वज़न {weight} किलो। आज लगे टीके: {given}। बाकी टीके: {due}। अगली विज़िट {next}।{danger} सही है तो बोलिए 'हाँ, सेव करो', नहीं तो गलती बताइए।",
        "readback_danger": " खतरे का निशान: {signs}।",
        "updated": "ठीक है, {changes}। सही है तो बोलिए 'हाँ, सेव करो'।",
        "change_item": "{field} अब {value}",
        "what_wrong": "कौन सी जानकारी गलत है? सही बात बताइए।",
        "saved": "रिकॉर्ड सेव हो गया। अगली विज़िट {next}।{flag} अगले घर के लिए ID बताइए।",
        "saved_flag": " यह केस PHC रेफ़रल सूची में सबसे ऊपर है।",
        "danger_alert": "ध्यान दीजिए: {signs}, यह खतरे का लक्षण है। अभी PHC रेफ़र कीजिए। रिकॉर्ड पर लाल निशान लगा दिया है।",
        "advice": "मैं दवा, खुराक या इलाज की सलाह नहीं दे सकती। कृपया ANM या PHC डॉक्टर से पूछिए।",
        "repeat": "माफ़ कीजिए, समझ नहीं आया। फिर से बोलिए।",
        "none": "कोई नहीं",
        "missing": "नहीं बताया",
        "point": "पॉइंट",
        "and": " और ",
        "fields": {"weight_kg": "वज़न", "visit_type": "विज़िट", "vaccines_given_today": "आज लगे टीके",
                   "next_visit_date": "अगली विज़िट", "notes": "नोट"},
        "btype": {"newborn": "नवजात शिशु", "pregnant": "गर्भवती", "child": "बच्चा"},
        "visit": {"ANC": "ANC जांच", "HBNC": "नवजात विज़िट", "PNC": "प्रसव के बाद विज़िट", "IMMUNISATION": "टीकाकरण"},
        "months": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    },
    "kn": {
        "greet": "ನಮಸ್ಕಾರ. ನಾನು AI ಸಹಾಯಕಿ, ಮನುಷ್ಯಳಲ್ಲ. ನಿಮ್ಮ ಭೇಟಿಯ ದಾಖಲೆ ತುಂಬಲು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ಫಲಾನುಭವಿಯ ID ಅಥವಾ ಹೆಸರು ಹೇಳಿ.",
        "found": "{name}, ID {id}, {btype}. ಈಗ ಭೇಟಿಯ ವಿವರ ಹೇಳಿ.",
        "not_found": "ಈ ಫಲಾನುಭವಿ ಸಿಗಲಿಲ್ಲ. ID ಯನ್ನು ಒಂದೊಂದೇ ಅಂಕಿ ಮತ್ತೆ ಹೇಳಿ.",
        "ask_weight_kg": "ತೂಕ ಎಷ್ಟು?",
        "ask_visit_type": "ಇದು ಯಾವ ಭೇಟಿ: ANC ತಪಾಸಣೆ, ನವಜಾತ ಶಿಶು ಭೇಟಿ, ಅಥವಾ ಲಸಿಕೆ?",
        "weight_check": "ತೂಕ {w} ಕಿಲೋ ಸರಿ ಅನಿಸುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ತೂಕ ಮತ್ತೆ ಹೇಳಿ.",
        "readback": "ನಾನು ಓದಿ ಹೇಳುತ್ತೇನೆ. ID {id}. ಭೇಟಿ: {visit_type}. ತೂಕ {weight} ಕಿಲೋ. ಇಂದು ಹಾಕಿದ ಲಸಿಕೆ: {given}. ಬಾಕಿ ಲಸಿಕೆ: {due}. ಮುಂದಿನ ಭೇಟಿ {next}.{danger} ಸರಿ ಇದ್ದರೆ 'ಹೌದು, ಸೇವ್ ಮಾಡಿ' ಎನ್ನಿ, ಇಲ್ಲದಿದ್ದರೆ ತಪ್ಪು ಹೇಳಿ.",
        "readback_danger": " ಅಪಾಯದ ಚಿಹ್ನೆ: {signs}.",
        "updated": "ಸರಿ, {changes}. ಸರಿ ಇದ್ದರೆ 'ಹೌದು, ಸೇವ್ ಮಾಡಿ' ಎನ್ನಿ.",
        "change_item": "{field} ಈಗ {value}",
        "what_wrong": "ಯಾವ ಮಾಹಿತಿ ತಪ್ಪು? ಸರಿಯಾದದ್ದನ್ನು ಹೇಳಿ.",
        "saved": "ದಾಖಲೆ ಸೇವ್ ಆಯಿತು. ಮುಂದಿನ ಭೇಟಿ {next}.{flag} ಮುಂದಿನ ಮನೆಗೆ ID ಹೇಳಿ.",
        "saved_flag": " ಈ ಪ್ರಕರಣ PHC ರೆಫರಲ್ ಪಟ್ಟಿಯಲ್ಲಿ ಮೇಲಿದೆ.",
        "danger_alert": "ಗಮನಿಸಿ: {signs}, ಇದು ಅಪಾಯದ ಲಕ್ಷಣ. ಈಗಲೇ PHC ಗೆ ಕಳುಹಿಸಿ. ದಾಖಲೆಗೆ ಕೆಂಪು ಗುರುತು ಹಾಕಿದ್ದೇನೆ.",
        "advice": "ನಾನು ಔಷಧಿ, ಡೋಸ್ ಅಥವಾ ಚಿಕಿತ್ಸೆಯ ಸಲಹೆ ನೀಡಲಾರೆ. ದಯವಿಟ್ಟು ANM ಅಥವಾ PHC ವೈದ್ಯರನ್ನು ಕೇಳಿ.",
        "repeat": "ಕ್ಷಮಿಸಿ, ಅರ್ಥವಾಗಲಿಲ್ಲ. ಮತ್ತೆ ಹೇಳಿ.",
        "none": "ಯಾವುದೂ ಇಲ್ಲ",
        "missing": "ಹೇಳಿಲ್ಲ",
        "point": "ಪಾಯಿಂಟ್",
        "and": " ಮತ್ತು ",
        "fields": {"weight_kg": "ತೂಕ", "visit_type": "ಭೇಟಿ", "vaccines_given_today": "ಇಂದು ಹಾಕಿದ ಲಸಿಕೆ",
                   "next_visit_date": "ಮುಂದಿನ ಭೇಟಿ", "notes": "ಟಿಪ್ಪಣಿ"},
        "btype": {"newborn": "ನವಜಾತ ಶಿಶು", "pregnant": "ಗರ್ಭಿಣಿ", "child": "ಮಗು"},
        "visit": {"ANC": "ANC ತಪಾಸಣೆ", "HBNC": "ನವಜಾತ ಶಿಶು ಭೇಟಿ", "PNC": "ಹೆರಿಗೆ ನಂತರದ ಭೇಟಿ", "IMMUNISATION": "ಲಸಿಕೆ"},
        "months": ["ಜನವರಿ", "ಫೆಬ್ರವರಿ", "ಮಾರ್ಚ್", "ಏಪ್ರಿಲ್", "ಮೇ", "ಜೂನ್", "ಜುಲೈ", "ಆಗಸ್ಟ್", "ಸೆಪ್ಟೆಂಬರ್", "ಅಕ್ಟೋಬರ್", "ನವೆಂಬರ್", "ಡಿಸೆಂಬರ್"],
    },
}

VACCINE_SPOKEN = {
    "HepB-0": "Hepatitis B", "fIPV-1": "IPV 1", "fIPV-2": "IPV 2", "fIPV-3": "IPV 3",
    "RVV-1": "Rota 1", "RVV-2": "Rota 2", "RVV-3": "Rota 3", "VitA-1": "Vitamin A",
    "PCV-B": "PCV booster", "DPT-B1": "DPT booster", "OPV-B": "OPV booster", "Td-B": "Td booster",
}


def say(lang: str, key: str, **kw) -> str:
    return T[lang][key].format(**kw)


def word(lang: str, key: str):
    return T[lang][key]


def spoken_id(bid: str) -> str:
    return " ".join(bid)   # digit by digit, so TTS never reads "1042" as a big number


def spoken_weight(w: float, lang: str) -> str:
    s = f"{w:g}"
    if "." in s:
        a, b = s.split(".")
        return f"{a} {T[lang]['point']} {' '.join(b)}"
    return s


def spoken_date(d: date, lang: str) -> str:
    return f"{d.day} {T[lang]['months'][d.month - 1]}"


def spoken_vaccines(codes: list[str], lang: str) -> str:
    if not codes:
        return T[lang]["none"]
    return ", ".join(VACCINE_SPOKEN.get(c, c.replace("-", " ")) for c in codes)
