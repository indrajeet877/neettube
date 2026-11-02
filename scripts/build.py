#!/usr/bin/env python3
"""Build NEETTube's 72-chapter All-India NCERT NEET UG, AIIMS, Medical & PCB Boards YouTube index (data/videos.json).

Pure Python 3 standard library. Run from anywhere:

    python3 scripts/build.py --self-test
    python3 scripts/build.py
    python3 scripts/build.py --fresh

Queries YouTube's public web search endpoint across all 72 canonical NCERT NEET UG & PCB
chapters across 4 separate subjects (Botany: 17, Zoology: 15, Physics: 20, Chemistry: 20)
using clean, focused YouTube queries across both YouTube's native Playlist filter
(sp=EgIQAw==) and Long-Form Lecture filter (sp=EgIYAg==), plus educator, regional-language,
Medical/AIIMS/Nursing, State CET, and Class 12 PCB Board sweeps across all popular Indian
languages (Hinglish, English, Hindi, Tamil, Malayalam, Telugu, Kannada, Bengali, Marathi,
Gujarati, Odia, Punjabi). Enforces a strict Verified Educator/Institute Channel allowlist,
chapter-matching, cross-subject guards, JEE-Advanced/Class-6-10/clickbait rejection, and
100% pure YouTube trend ranking (ZERO artificial institute priority).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
OUT_PATH = ROOT / "data" / "videos.json"

INNERTUBE_SEARCH = "https://www.youtube.com/youtubei/v1/search"
SP_PLAYLIST_ONLY = "EgIQAw=="  # YouTube native Type: Playlist protobuf filter
SP_LONG_VIDEOS = "EgIYAg=="    # YouTube native Duration: >20 minutes protobuf filter

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

CANONICAL_LANGUAGES = (
    "Hinglish",
    "English",
    "Hindi",
    "Tamil",
    "Malayalam",
    "Telugu",
    "Kannada",
    "Bengali",
    "Marathi",
    "Gujarati",
    "Odia",
    "Punjabi",
)

CANONICAL_EXAMS = (
    "NEET UG",
    "NEET + AIIMS",
    "Medical, Nursing & State CET",
    "Class 12 & Boards",
)


def _ssl_context() -> ssl.SSLContext:
    for cafile in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.exists(cafile):
            return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


SSL_CTX = _ssl_context()
_lock = threading.Lock()
STATS = {"requests": 0, "cached": 0}

# ---------------------------------------------------------------------------
# Complete 72-Chapter Canonical NCERT NEET UG & PCB Syllabus Taxonomy
# Subjects: Botany (17), Zoology (15), Physics (20), Chemistry (20)
# Tuple:
#   (ch_no, subject, unit, class_level, weightage, syllabus_scope, chapter_name,
#    match_regex, core_search_phrase, alt_search_phrase)
# ---------------------------------------------------------------------------
SYLLABUS: list[tuple[int, str, str, str, str, str, str, str, str, str]] = [
    # ========================== BOTANY (17 Chapters) ==========================
    (
        1, "Botany", "Diversity in Living World", "Class 11", "Medium", "NCERT Core",
        "Living World",
        r"\b(living world|taxonom(?:y|ic)|binomial nomenclature|systematics)\b|(?:जीव\s*जगत(?!\s*का\s*वर्गीकरण)|द्विपद\s*नामकरण)",
        "The Living World Class 11 Biology",
        "Living World Botany",
    ),
    (
        2, "Botany", "Diversity in Living World", "Class 11", "High", "NCERT Core",
        "Biological Classification",
        r"\b(biological classification|five kingdom|monera|protista|fungi\b|viruses|viroids|lichens)\b|(?:जीव\s*जगत\s*का\s*वर्गीकरण|जैविक\s*वर्गीकरण|मोनेरा|प्रोटिस्टा|कवक)",
        "Biological Classification Class 11",
        "Biological Classification Botany",
    ),
    (
        3, "Botany", "Diversity in Living World", "Class 11", "High", "NCERT Core",
        "Plant Kingdom",
        r"\b(plant kingdom|algae\b|bryophytes?|pteridophytes?|gymnosperms?|angiosperms?)\b|(?:पादप\s*जगत|वनस्पति\s*जगत|शैवाल|ब्रायोफाइटा|टेरिडोफाइटा)",
        "Plant Kingdom Class 11 Biology",
        "Plant Kingdom Botany",
    ),
    (
        4, "Botany", "Structural Organisation in Plants", "Class 11", "High", "NCERT Core",
        "Morphology of Flowering Plants",
        r"\b(morphology of flowering|plant morphology|morphology\s+class\s*11|inflorescence|placentation|plant families)\b|(?:पुष्पी\s*पादपों\s*की\s*आकारिकी|पादप\s*आकारिकी)",
        "Morphology of Flowering Plants",
        "Morphology of Flowering Plants Botany",
    ),
    (
        5, "Botany", "Structural Organisation in Plants", "Class 11", "High", "NCERT Core",
        "Anatomy of Flowering Plants",
        r"\b(anatomy of flowering|plant anatomy|meristem\w*|plant tissues|vascular bundles|secondary growth|dicot|monocot)\b|(?:पुष्पी\s*पादपों\s*का\s*शारीर|पादप\s*शारीर)",
        "Anatomy of Flowering Plants",
        "Anatomy of Flowering Plants Botany",
    ),
    (
        6, "Botany", "Cell Structure & Function", "Class 11", "Very High", "NCERT Core",
        "Cell: The Unit of Life",
        r"\b(unit of life|cell\s*:\s*the unit|cell biology|cell structure|prokaryotic|eukaryotic|endomembrane|organelles)\b|(?:कोशिका\s*[:|-]?\s*जीवन\s*की\s*इकाई|जीवन\s*की\s*इकाई|कोशिका\s*संरचना|कोशिका)",
        "Cell The Unit of Life Class 11",
        "Cell The Unit of Life Botany",
    ),
    (
        7, "Botany", "Cell Structure & Function", "Class 11", "Very High", "NCERT Core",
        "Cell Cycle & Cell Division",
        r"\b(cell cycle|cell division|mitosis|meiosis)\b|(?:कोशिका\s*चक्र|कोशिका\s*विभाजन|समसूत्री|अर्धसूत्री)",
        "Cell Cycle and Cell Division",
        "Cell Cycle Cell Division Mitosis Meiosis",
    ),
    (
        8, "Botany", "Plant Physiology", "Class 11", "High", "NCERT Core",
        "Photosynthesis in Higher Plants",
        r"\b(photosynthesis|light reaction|calvin cycle|c3\s*(?:and|&)?\s*c4|photorespiration|hatch\s*(?:and|&)?\s*slack)\b|(?:प्रकाश[\s-]*संश्लेषण)",
        "Photosynthesis in Higher Plants",
        "Photosynthesis Class 11 Biology",
    ),
    (
        9, "Botany", "Plant Physiology", "Class 11", "High", "NCERT Core",
        "Respiration in Plants",
        r"\b(respiration in plants|plant respiration|glycolysis|krebs\s*cycle|tca\s*cycle|electron transport.*plant|oxidative phosphorylation)\b|(?:पादपों?\s*में\s*श्वसन|पादप\s*श्वसन|ग्लाइकोलाइसिस|क्रेब्स\s*चक्र)",
        "Respiration in Plants Class 11",
        "Respiration in Plants Botany",
    ),
    (
        10, "Botany", "Plant Physiology", "Class 11", "Medium", "NCERT Core",
        "Plant Growth & Development",
        r"\b(plant growth|plant hormones|phytohormones|auxins?|gibberellins?|cytokinins?|photoperiodism|vernalisation|plant water relations)\b|(?:पादप\s*वृद्धि|पादप\s*हार्मोन)",
        "Plant Growth and Development",
        "Plant Growth and Development Botany",
    ),
    (
        11, "Botany", "Plant Reproduction", "Class 12", "Very High", "NCERT Core",
        "Sexual Reproduction in Flowering Plants",
        r"\b(sexual reproduction in flowering|reproduction in flowering|reproduction in (?:lower and )?higher plants|pollination|double fertilization|microsporogenesis|megasporogenesis|endosperm|apomixis)\b|(?:पुष्पी\s*पादपों\s*में\s*लैंगिक\s*(?:प्र)?जनन|परागण|द्विनिषेचन)",
        "Sexual Reproduction in Flowering Plants",
        "Sexual Reproduction in Flowering Plants Class 12",
    ),
    (
        12, "Botany", "Genetics", "Class 12", "Very High", "High-Yield NCERT",
        "Principles of Inheritance & Variation",
        r"\b(principles? of inheritance|inheritance\s*(?:and|&)\s*variation|mendel\w*|linkage|recombination|pedigree|chromosomal disorders)\b|(?:वंशागति\s*(?:तथा|और|एवं|के)\s*(?:विविधता|सिद्धांत)|आनुवंशिकी|मेण्डल|मेंडल)",
        "Principles of Inheritance and Variation",
        "Genetics Principles of Inheritance Class 12",
    ),
    (
        13, "Botany", "Genetics", "Class 12", "Very High", "High-Yield NCERT",
        "Molecular Basis of Inheritance",
        r"\b(molecular basis of inheritance|molecular basis|dna replication|transcription|translation|genetic code|lac operon|human genome)\b|(?:वंशागति\s*का\s*आणविक\s*आधार|आणविक\s*आधार|डीएनए\s*प्रतिकृति|अनुलेखन)",
        "Molecular Basis of Inheritance",
        "Molecular Basis of Inheritance Class 12",
    ),
    (
        14, "Botany", "Biology in Human Welfare", "Class 12", "Medium", "NCERT Core",
        "Microbes in Human Welfare",
        r"\b(microbes in human welfare|sewage treatment|biogas|biofertilizers?|biocontrol agents)\b|(?:मानव\s*कल्याण\s*में\s*सूक्ष्मजीव|सूक्ष्मजीव)",
        "Microbes in Human Welfare",
        "Microbes in Human Welfare Class 12",
    ),
    (
        15, "Botany", "Ecology & Environment", "Class 12", "High", "NCERT Core",
        "Organisms & Populations",
        r"\b(organisms?\s*(?:and|&)\s*populations?|population interactions?|population attributes|mutualism|commensalism|predation)\b|(?:जीव\s*(?:और|तथा|एवं)\s*समष्टियाँ|समष्टियाँ)",
        "Organisms and Populations Class 12",
        "Organisms and Populations Ecology",
    ),
    (
        16, "Botany", "Ecology & Environment", "Class 12", "High", "NCERT Core",
        "Ecosystem",
        r"\b(ecosystems?\b|ecological pyramids?|energy flow|decomposition|productivity.*ecology|nutrient cycling)\b|(?:पारितंत्र|पारिस्थितिकी\s*तंत्र|पारिस्थितिकी)",
        "Ecosystem Class 12 Biology",
        "Ecosystem Botany Ecology",
    ),
    (
        17, "Botany", "Ecology & Environment", "Class 12", "High", "NCERT Core",
        "Biodiversity & Conservation",
        r"\b(biodiversity|conservation|species area|sacred groves|in[- ]situ|ex[- ]situ|red data)\b|(?:जैव\s*विविधता\s*(?:एवं|और|तथा)?\s*संरक्षण|जैव\s*विविधता)",
        "Biodiversity and Conservation Class 12",
        "Biodiversity and Conservation Ecology",
    ),

    # ========================= ZOOLOGY (15 Chapters) =========================
    (
        18, "Zoology", "Animal Diversity & Organisation", "Class 11", "Very High", "High-Yield NCERT",
        "Animal Kingdom",
        r"\b(animal kingdom|non[- ]?chordates?|chordates?|porifera|cnidaria|arthropoda|mollusca|vertebrata)\b|(?:प्राणि\s*जगत|जंतु\s*जगत)",
        "Animal Kingdom Class 11 Biology",
        "Animal Kingdom Zoology",
    ),
    (
        19, "Zoology", "Animal Diversity & Organisation", "Class 11", "High", "NCERT Core",
        "Structural Organisation in Animals",
        r"\b(structural organi[sz]ation in animals|animal tissues?|cockroach|frog\b|epithelial tissue|connective tissue)\b|(?:प्राणियों\s*में\s*संरचनात्मक\s*संगठन|जंतु\s*ऊतक|कॉकरोच|मेंढक)",
        "Structural Organisation in Animals",
        "Animal Tissues Frog Cockroach Zoology",
    ),
    (
        20, "Zoology", "Cell & Biomolecules", "Class 11", "Very High", "High-Yield NCERT",
        "Biomolecules",
        r"\b(biomolecules?|enzymes?\b|metabolites?|polysaccharides?|nucleic acids?)\b|(?:जैव[\s-]*अणु|एंजाइम)",
        "Biomolecules Class 11 Biology",
        "Biomolecules Zoology Enzymes",
    ),
    (
        21, "Zoology", "Human Physiology", "Class 11", "High", "NCERT Core",
        "Breathing & Exchange of Gases",
        r"\b(breathing\s*(?:and|&)\s*exchange|exchange of gases|human respiratory|respiratory volumes|oxygen dissociation)\b|(?:श्वसन\s*(?:और|एवं|तथा)\s*गैसों\s*का\s*विनिमय|गैसों\s*का\s*विनिमय|मानव\s*श्वसन)",
        "Breathing and Exchange of Gases",
        "Breathing and Exchange of Gases Zoology",
    ),
    (
        22, "Zoology", "Human Physiology", "Class 11", "High", "NCERT Core",
        "Body Fluids & Circulation",
        r"\b(body fluids?\s*(?:and|&)?\s*circulation|respiration\s*(?:and|&)\s*circulation|cardiac cycle|\becg\b|human heart|blood groups?|double circulation)\b|(?:शरीर\s*द्रव\s*(?:तथा|एवं|और)\s*परिसंचरण|रक्त\s*परिसंचरण|मानव\s*हृदय)",
        "Body Fluids and Circulation",
        "Body Fluids and Circulation Zoology",
    ),
    (
        23, "Zoology", "Human Physiology", "Class 11", "High", "NCERT Core",
        "Excretory Products & Elimination",
        r"\b(excretory products?|elimination|human excretory|nephron|urine formation|counter current|osmoregulation)\b|(?:उत्सर्जी\s*उत्पाद|उत्सर्जन\s*तंत्र|नेफ्रॉन)",
        "Excretory Products and their Elimination",
        "Excretory Products Elimination Zoology",
    ),
    (
        24, "Zoology", "Human Physiology", "Class 11", "High", "NCERT Core",
        "Locomotion & Movement",
        r"\b(locomotion\s*(?:and|&)?\s*movement|muscle contraction|sliding filament|skeletal system|joints\b|sarcomere)\b|(?:गमन\s*(?:एवं|और|तथा)\s*संचलन|कंकाल\s*तंत्र|पेशी\s*संकुचन)",
        "Locomotion and Movement Class 11",
        "Locomotion and Movement Zoology",
    ),
    (
        25, "Zoology", "Human Physiology", "Class 11", "High", "NCERT Core",
        "Neural Control & Coordination",
        r"\b(neural control|control\s*(?:and|&)\s*coordination|nervous system|nerve impulse|synapse|human brain|action potential)\b|(?:तंत्रिकीय\s*नियंत्रण|तंत्रिका\s*तंत्र|मानव\s*मस्तिष्क)",
        "Neural Control and Coordination",
        "Neural Control and Coordination Zoology",
    ),
    (
        26, "Zoology", "Human Physiology", "Class 11", "High", "NCERT Core",
        "Chemical Coordination & Integration",
        r"\b(chemical coordination|endocrine|pituitary|thyroid|adrenal|hormone action)\b|(?:रासायनिक\s*समन्वय|अंतःस्रावी\s*तंत्र)",
        "Chemical Coordination and Integration",
        "Endocrine System Chemical Coordination",
    ),
    (
        27, "Zoology", "Human Reproduction", "Class 12", "Very High", "High-Yield NCERT",
        "Human Reproduction",
        r"\b(human reproduction|reproduction in (?:lower and )?higher animals|gametogenesis|spermatogenesis|oogenesis|menstrual cycle|fertilization and implantation|parturition)\b|(?:मानव\s*जनन|मानव\s*प्रजनन|युग्मकजनन|आर्तव\s*चक्र)",
        "Human Reproduction Class 12",
        "Human Reproduction Zoology",
    ),
    (
        28, "Zoology", "Human Reproduction", "Class 12", "Medium", "NCERT Core",
        "Reproductive Health",
        r"\b(reproductive health|contracepti\w*|amniocentesis|infertility|medical termination|\bmtp\b|assisted reproductive)\b|(?:जनन\s*स्वास्थ्य|गर्भनिरोधक)",
        "Reproductive Health Class 12",
        "Reproductive Health Zoology",
    ),
    (
        29, "Zoology", "Evolution & Human Health", "Class 12", "High", "NCERT Core",
        "Evolution",
        r"\b(evolution\b|hardy[- ]weinberg|natural selection|darwin\w*|adaptive radiation|human evolution|origin of life)\b|(?:जैव\s*विकास|विकास\s*कक्षा\s*12|हार्डी\s*वीनबर्ग|डार्विन)",
        "Evolution Class 12 Biology",
        "Evolution Zoology Class 12",
    ),
    (
        30, "Zoology", "Evolution & Human Health", "Class 12", "Very High", "High-Yield NCERT",
        "Human Health & Disease",
        r"\b(human health\s*(?:and|&)?\s*diseases?|immunity|aids\b|cancer\b|malaria|drug\s*(?:and|&)\s*alcohol|antibodies)\b|(?:मानव\s*स्वास्थ्य\s*(?:तथा|एवं|और)\s*रोग|प्रतिरक्षा|एड्स|कैंसर|मलेरिया)",
        "Human Health and Disease Class 12",
        "Human Health and Disease Zoology",
    ),
    (
        31, "Zoology", "Biotechnology", "Class 12", "Very High", "High-Yield NCERT",
        "Biotechnology: Principles & Processes",
        r"\b(biotechnology\s*[:|-]?\s*principles?|principles?\s*(?:and|&)\s*process(?:es)?|recombinant dna|\bpcr\b|gel electrophoresis|cloning vectors?|restriction enzymes?|bioreactors?)\b|(?:जैव\s*प्रौद्योगिकी\s*[:|-]?\s*सिद्धांत|जैव\s*प्रौद्योगिकी(?!\s*(?:एवं|और|तथा)\s*उसके))",
        "Biotechnology Principles and Processes",
        "Biotechnology Principles Processes Class 12",
    ),
    (
        32, "Zoology", "Biotechnology", "Class 12", "Very High", "High-Yield NCERT",
        "Biotechnology & Its Applications",
        r"\b(biotechnology\s*(?:and|&|:|-)?\s*its\s*applications?|applications? of biotechnology|bt\s*cotton|gene therapy|rna interference|genetically engineered insulin|transgenic animals|biopiracy)\b|(?:जैव\s*प्रौद्योगिकी\s*(?:एवं|और|तथा)\s*उसके\s*(?:उपयोग|अनुप्रयोग)|बीटी\s*कपास|जीन\s*चिकित्सा)",
        "Biotechnology and its Applications",
        "Biotechnology Applications Class 12",
    ),

    # ========================= PHYSICS (20 Chapters) =========================
    (
        33, "Physics", "Mechanics", "Class 11", "High", "NEET UG Core",
        "Units & Measurements",
        r"\b(units?\s*(?:and|&)\s*measurements?|units?\s*(?:and|&)\s*dimensions?|dimensional|error analysis|significant figures|vernier|screw gauge|basic maths?\s*(?:for|in)?\s*physics)\b|(?:मात्रक\s*(?:एवं|और|तथा)\s*मापन|विमीय\s*विश्लेषण|त्रुटि\s*विश्लेषण)",
        "Units and Measurements Physics",
        "Units Dimensions Error Analysis Vernier",
    ),
    (
        34, "Physics", "Mechanics", "Class 11", "High", "NEET UG Core",
        "Motion in a Straight Line",
        r"\b(motion in a straight line|motion in 1\s*-?\s*d|motion in one dimension|rectilinear motion|1d\s+kinematics|kinematics\s+1d)\b|(?:सरल\s*रेखा\s*में\s*गति|एकविमीय\s*गति)",
        "Motion in a Straight Line Class 11",
        "Kinematics 1D Motion in Straight Line",
    ),
    (
        35, "Physics", "Mechanics", "Class 11", "High", "NEET UG Core",
        "Motion in a Plane & Projectile",
        r"\b(motion in a plane|motion in 2\s*-?\s*d|motion in two dimensions|projectile|2d\s+kinematics|kinematics\s+2d|rain\s*man|river\s*boat)\b|(?:समतल\s*में\s*गति|प्रक्षेप्य\s*गति)",
        "Motion in a Plane Class 11 Physics",
        "Projectile Motion Kinematics 2D",
    ),
    (
        36, "Physics", "Mechanics", "Class 11", "High", "NEET UG Core",
        "Laws of Motion & Friction",
        r"\b(laws? of motion|newton'?s laws?|\bnlm\b|friction|pseudo force|pulley|circular banking)\b|(?:गति\s*के\s*नियम|घर्षण|न्यूटन\s*के\s*गति)",
        "Laws of Motion Class 11 Physics",
        "Newton Laws of Motion Friction NLM",
    ),
    (
        37, "Physics", "Mechanics", "Class 11", "High", "NEET UG Core",
        "Work, Energy & Power",
        r"\b(work[, ]*(?:energy|power)|work\s*(?:and|&)\s*energy|\bwep\b|\bwpe\b|vertical circular motion)\b|(?:कार्य[, ]*ऊर्जा\s*(?:एवं|और|तथा)?\s*शक्ति|कार्य\s*ऊर्जा)",
        "Work Energy and Power Physics",
        "Work Power Energy Class 11",
    ),
    (
        38, "Physics", "Mechanics", "Class 11", "Very High", "NEET UG Core",
        "System of Particles & Rotational Motion",
        r"\b(system of particles|rotational motion|rotational dynamics|rotational\b|cent(?:re|er) of mass|\bcom\b|moment of inertia|rigid body|torque|rolling motion|collisions?)\b|(?:कणों\s*के\s*निकाय|घूर्णी\s*गति|द्रव्यमान\s*केंद्र|जड़त्व\s*आघूर्ण)",
        "System of Particles and Rotational Motion",
        "Rotational Motion Centre of Mass Physics",
    ),
    (
        39, "Physics", "Mechanics", "Class 11", "High", "NEET UG Core",
        "Gravitation",
        r"\b(gravitation\w*|kepler|escape velocity|orbital velocity|satellites?)\b|(?:गुरुत्वाकर्षण|पलायन\s*वेग|केपलर)",
        "Gravitation Class 11 Physics",
        "Gravitation Physics",
    ),
    (
        40, "Physics", "Properties of Matter & Thermodynamics", "Class 11", "High", "NEET UG Core",
        "Mechanical Properties of Solids & Fluids",
        r"\b(mechanical properties of (?:solids|fluids)|elasticity|fluid mechanics|fluids?\b|surface tension|viscosity|bernoulli|young'?s modulus)\b|(?:ठोसों\s*के\s*यांत्रिक\s*गुण|तरलों\s*के\s*यांत्रिक\s*गुण|प्रत्यास्थता|पृष्ठ\s*तनाव|श्यानता)",
        "Mechanical Properties of Solids and Fluids",
        "Fluid Mechanics Elasticity Surface Tension",
    ),
    (
        41, "Physics", "Properties of Matter & Thermodynamics", "Class 11", "High", "NEET UG Core",
        "Thermal Properties & Heat Transfer",
        r"\b(thermal properties|thermal physics|heat transfer|calorimetry|thermal expansion|conduction|radiation|newton'?s law of cooling|wein)\b|(?:द्रव्य\s*के\s*तापीय\s*गुण|ऊष्मा\s*स्थानांतरण|कैलोरीमिति)",
        "Thermal Properties of Matter Physics",
        "Heat Transfer Calorimetry Thermal Expansion",
    ),
    (
        42, "Physics", "Properties of Matter & Thermodynamics", "Class 11", "Very High", "NEET UG Core",
        "Thermodynamics & KTG",
        r"\b(kinetic theory|\bktg\b|thermodynamics|carnot|heat engine|isothermal|adiabatic)\b|(?:ऊष्मागतिकी|अणुगति\s*सिद्धांत)",
        "Thermodynamics and KTG Physics",
        "Kinetic Theory of Gases Thermodynamics Physics",
    ),
    (
        43, "Physics", "Oscillations & Waves", "Class 11", "High", "NEET UG Core",
        "Oscillations (SHM)",
        r"\b(oscillations?|simple harmonic|\bshm\b|simple pendulum|spring block)\b|(?:दोलन|सरल\s*आवर्त\s*गति)",
        "Oscillations Class 11 Physics",
        "Simple Harmonic Motion SHM Physics",
    ),
    (
        44, "Physics", "Oscillations & Waves", "Class 11", "High", "NEET UG Core",
        "Waves & Sound",
        r"\b(waves?\s*(?:and|&)\s*sound|sound waves?|string waves?|standing waves?|stationary waves?|superposition of waves|wave motion|organ pipe|beats\b|doppler|\bwaves\b)\b|(?:तरंगें|ध्वनि\s*तरंग|डॉपलर)",
        "Waves Class 11 Physics",
        "Sound Waves Organ Pipe Beats Doppler",
    ),
    (
        45, "Physics", "Electrodynamics", "Class 12", "Very High", "NEET UG Core",
        "Electric Charges, Fields & Potential",
        r"\b(electric charges|electric fields?|electrostatics?|electrostatic potential|electric potential|gauss'?s?\s*law|electric dipole|coulomb)\b|(?:वैद्युत\s*आवेश|विद्युत\s*आवेश|स्थिर\s*वैद्युतिकी|स्थिरवैद्युत\s*विभव|विद्युत\s*विभव|गाउस\s*का\s*नियम)",
        "Electric Charges and Fields Class 12",
        "Electrostatic Potential Electrostatics Physics",
    ),
    (
        46, "Physics", "Electrodynamics", "Class 12", "Very High", "NEET UG Core",
        "Capacitors & Current Electricity",
        r"\b(capacitors?|capacitance|current electricity|kirchhoff|wheatstone|meter bridge|potentiometer|ohm'?s law)\b|(?:संधारित्र|धारिता|विद्युत\s*धारा|वैद्युत\s*धारा|किरचॉफ|विभवमापी)",
        "Current Electricity Class 12 Physics",
        "Capacitors and Capacitance Current Electricity",
    ),
    (
        47, "Physics", "Electrodynamics", "Class 12", "Very High", "NEET UG Core",
        "Moving Charges & Magnetism",
        r"\b(moving charges|magnetic effects? of current|magnetic fields? due to electric current|biot[- ]savart|ampere|lorentz|galvanometer|solenoid)\b|(?:गतिमान\s*आवेश|विद्युत\s*धारा\s*का\s*चुंबकीय\s*प्रभाव|बायो[- ]सेवर्ट)",
        "Moving Charges and Magnetism Class 12",
        "Magnetic Effects of Current Physics",
    ),
    (
        48, "Physics", "Electrodynamics", "Class 12", "High", "NEET UG Core",
        "Magnetism, Matter & EMI",
        r"\b(magnetism\s*(?:and|&)\s*matter|magnetic materials|electromagnetic induction|\bemi\b|faraday|lenz|inductance|bar magnet|magnetic properties|motional emf)\b|(?:चुंबकत्व\s*(?:एवं|और|तथा)\s*द्रव्य|विद्युत\s*चुंबकीय\s*प्रेरण|वैद्युतचुंबकीय\s*प्रेरण|फैराडे)",
        "Electromagnetic Induction Class 12 Physics",
        "Magnetism and Matter EMI Physics",
    ),
    (
        49, "Physics", "Electrodynamics", "Class 12", "High", "NEET UG Core",
        "Alternating Current & EM Waves",
        r"\b(alternating current|ac\s+circuits?|\bac\b\s*(?:class\s*12|physics|one\s*shot|in\s+one\s*shot|neet|circuit)|lcr|transformer|electromagnetic waves?|\bem\s+waves?\b)\b|(?:प्रत्यावर्ती\s*धारा|ट्रांसफार्मर|विद्युत\s*चुंबकीय\s*तरंगें|वैद्युतचुंबकीय\s*तरंगें)",
        "Alternating Current Class 12 Physics",
        "Electromagnetic Waves Alternating Current",
    ),
    (
        50, "Physics", "Optics & Modern Physics", "Class 12", "Very High", "NEET UG Core",
        "Ray Optics & Optical Instruments",
        r"\b(ray optics|geometrical optics|optical instruments?|refraction|prism|lens|mirror|total internal reflection|microscope|telescope)\b|(?:किरण\s*प्रकाशिकी|प्रकाशिक\s*यंत्र|प्रकाशिकी)",
        "Ray Optics and Optical Instruments",
        "Ray Optics Class 12 Physics",
    ),
    (
        51, "Physics", "Optics & Modern Physics", "Class 12", "High", "NEET UG Core",
        "Wave Optics",
        r"\b(wave optics|ydse|young'?s double|interference|diffraction|polarisation|polarization|huygens)\b|(?:तरंग\s*प्रकाशिकी|व्यतिकरण|विवर्तन|हाइगेंस)",
        "Wave Optics Class 12 Physics",
        "Wave Optics YDSE Interference",
    ),
    (
        52, "Physics", "Optics & Modern Physics", "Class 12", "Very High", "High-Yield NCERT",
        "Modern Physics: Atoms, Nuclei & Semiconductors",
        r"\b(modern physics|dual nature|photoelectric|atoms\b|nuclei\b|nuclear physics|radioactivity|semiconductors?|semiconductor devices|logic gates?|p[- ]?n junction|diodes?)\b|(?:आधुनिक\s*भौतिकी|विकिरण\s*तथा\s*द्रव्य\s*की\s*द्वैत\s*प्रकृति|प्रकाश\s*विद्युत\s*प्रभाव|नाभिक|अर्धचालक|लॉजिक\s*गेट)",
        "Modern Physics Semiconductors Class 12",
        "Dual Nature Atoms Nuclei Semiconductor",
    ),

    # ======================== CHEMISTRY (20 Chapters) ========================
    (
        53, "Chemistry", "Physical Chemistry", "Class 11", "High", "NEET UG Core",
        "Some Basic Concepts & Mole Concept",
        r"\b(some basic concepts|basic concepts of chemistry|mole concept|stoichiometry|limiting reagent|concentration terms|empirical formula)\b|(?:रसायन\s*विज्ञान\s*की\s*कुछ\s*मूल\s*अवधारणाएँ|मोल\s*अवधारणा|मोल\s*संकल्पना)",
        "Mole Concept Some Basic Concepts Chemistry",
        "Some Basic Concepts of Chemistry Class 11",
    ),
    (
        54, "Chemistry", "Physical Chemistry", "Class 11", "High", "NEET UG Core",
        "Structure of Atom",
        r"\b(structure of atom|atomic structure|quantum numbers|bohr'?s?\s*model|electronic configuration|de broglie.*atom|schrodinger)\b|(?:परमाणु\s*की\s*संरचना|परमाणु\s*संरचना|क्वांटम\s*संख्या|बोर\s*मॉडल)",
        "Structure of Atom Class 11 Chemistry",
        "Atomic Structure Chemistry",
    ),
    (
        55, "Chemistry", "Inorganic Chemistry", "Class 11", "High", "NCERT Core",
        "Periodic Classification",
        r"\b(periodic classification|periodic table|periodicity|classification of elements|periodic properties|ionization enthalpy|electronegativity)\b|(?:तत्वों\s*का\s*वर्गीकरण|आवर्त\s*सारणी|आवर्ती\s*गुण)",
        "Periodic Table Classification of Elements",
        "Periodic Classification Class 11 Chemistry",
    ),
    (
        56, "Chemistry", "Inorganic Chemistry", "Class 11", "Very High", "High-Yield NCERT",
        "Chemical Bonding & Molecular Structure",
        r"\b(chemical bonding|molecular structure|vsepr|hybridi[sz]ation|molecular orbital|\bmot\b|dipole moment|fajan)\b|(?:रासायनिक\s*आबंधन|आणविक\s*संरचना|संकरण)",
        "Chemical Bonding and Molecular Structure",
        "Chemical Bonding Class 11 Chemistry",
    ),
    (
        57, "Chemistry", "Physical Chemistry", "Class 11", "Very High", "NEET UG Core",
        "Chemical Thermodynamics",
        r"\b(thermodynamics|thermochemistry|enthalpy|entropy|gibbs|hess'?s?\s*law)\b|(?:रासायनिक\s*ऊष्मागतिकी|ऊष्मारसायन|एंथैल्पी)",
        "Thermodynamics Class 11 Chemistry",
        "Chemical Thermodynamics Thermochemistry",
    ),
    (
        58, "Chemistry", "Physical Chemistry", "Class 11", "Very High", "NEET UG Core",
        "Chemical & Ionic Equilibrium",
        r"\b(chemical equilibri\w*|ionic equilibri\w*|\bequilibri(?:um|a)\b|le chatelier|buffer|solubility product|\bph\b|salt hydrolysis)\b|(?:साम्यावस्था|रासायनिक\s*साम्य|आयनिक\s*साम्य|बफर\s*विलयन)",
        "Chemical and Ionic Equilibrium Chemistry",
        "Equilibrium Class 11 Chemistry Ionic",
    ),
    (
        59, "Chemistry", "Physical Chemistry", "Class 12", "Very High", "NEET UG Core",
        "Redox Reactions & Electrochemistry",
        r"\b(redox reactions?|redox\b|oxidation number|electrochemistry|nernst|galvanic|electrolytic|kohlrausch|conductance)\b|(?:अपचयोपचय|रेडॉक्स|वैद्युत\s*रसायन|विद्युत\s*रसायन|नर्नस्ट)",
        "Electrochemistry Class 12 Chemistry",
        "Redox Reactions and Electrochemistry",
    ),
    (
        60, "Chemistry", "Physical Chemistry", "Class 12", "High", "NEET UG Core",
        "Solutions & Colligative Properties",
        r"\b(liquid solutions?|solutions?\b|colligative|raoult|van'?t\s*hoff|henry'?s\s*law)\b|(?:विलयन|अणुसंख्य\s*गुणधर्म|राउल्ट)",
        "Solutions Class 12 Chemistry",
        "Liquid Solutions Colligative Properties",
    ),
    (
        61, "Chemistry", "Physical Chemistry", "Class 12", "High", "NEET UG Core",
        "Chemical Kinetics",
        r"\b(chemical kinetics|\bkinetics\b|rate law|first order|zero order|arrhenius|order of reaction|half life)\b|(?:रासायनिक\s*बलगतिकी|अभिक्रिया\s*की\s*कोटि|अर्ध\s*आयु)",
        "Chemical Kinetics Class 12 Chemistry",
        "Chemical Kinetics Chemistry",
    ),
    (
        62, "Chemistry", "Inorganic Chemistry", "Class 12", "High", "NCERT Core",
        "p-Block Elements",
        r"\b(p[- ]?block|group\s*(?:13|14|15|16|17|18)|boron family|carbon family|nitrogen family|oxygen family|halogens|noble gases)\b|(?:पी[- ]?ब्लॉक|p[- ]?ब्लॉक)",
        "p Block Elements Chemistry",
        "p Block Class 11 12 Inorganic",
    ),
    (
        63, "Chemistry", "Inorganic Chemistry", "Class 12", "High", "NCERT Core",
        "d- & f-Block Elements",
        r"\b(d\s*(?:and|&)\s*f\s*[- ]?block|d[- ]block|f[- ]block|transition elements|inner transition|lanthanoids|actinoids|kmno4|k2cr2o7)\b|(?:डी\s*(?:एवं|और|तथा)\s*एफ\s*ब्लॉक|d\s*(?:एवं|और)\s*f\s*ब्लॉक|संक्रमण\s*तत्व)",
        "d and f Block Elements Class 12",
        "d and f Block Inorganic Chemistry",
    ),
    (
        64, "Chemistry", "Inorganic Chemistry", "Class 12", "Very High", "High-Yield NCERT",
        "Coordination Compounds",
        r"\b(coordination compounds?|coordination chemistry|crystal field|\bcft\b|werner|valence bond.*coordination|ligands?)\b|(?:उपसहसंयोजन\s*यौगिक|उपसहसंयोजन|उपसहसंयोजक)",
        "Coordination Compounds Class 12",
        "Coordination Compounds Inorganic Chemistry",
    ),
    (
        65, "Chemistry", "Organic Chemistry", "Class 11", "Very High", "High-Yield NCERT",
        "Purification & General Organic Chemistry (GOC)",
        r"\b(general organic chemistry|\bgoc\b|purification.*organic|inductive|resonance|hyperconjugation|mesomeric|aromaticity|carbocation|reaction intermediates)\b|(?:सामान्य\s*कार्बनिक\s*रसायन|प्रेरणिक\s*प्रभाव|अनुनाद)",
        "General Organic Chemistry GOC",
        "Purification and GOC Organic Chemistry",
    ),
    (
        66, "Chemistry", "Organic Chemistry", "Class 11", "High", "NEET UG Core",
        "IUPAC & Isomerism",
        r"\b(iupac|nomenclature|isomerism|stereoisomerism|optical isomerism|geometrical isomerism|conformational|chirality)\b|(?:आईयूपीएसी|समावयवता|त्रिविम\s*समावयवता)",
        "IUPAC Nomenclature and Isomerism",
        "Isomerism Organic Chemistry",
    ),
    (
        67, "Chemistry", "Organic Chemistry", "Class 11", "Very High", "High-Yield NCERT",
        "Hydrocarbons",
        r"\b(hydrocarbons?|alkanes?|alkenes?|alkynes?|aromatic hydrocarbons?|benzene|ozonolysis|markovnikov)\b|(?:हाइड्रोकार्बन|एल्केन|एल्कीन|एल्काइन|बेंजीन)",
        "Hydrocarbons Class 11 Chemistry",
        "Hydrocarbons Organic Chemistry",
    ),
    (
        68, "Chemistry", "Organic Chemistry", "Class 12", "High", "NEET UG Core",
        "Haloalkanes & Haloarenes",
        r"\b(haloalkanes?|haloarenes?|halogen derivatives?|alkyl halides?|aryl halides?|sn1|sn2|grignard)\b|(?:हैलोएल्केन|हैलोएरीन|एल्किल\s*हैलाइड|ग्रिग्नार्ड)",
        "Haloalkanes and Haloarenes Class 12",
        "Haloalkanes Haloarenes Organic Chemistry",
    ),
    (
        69, "Chemistry", "Organic Chemistry", "Class 12", "High", "NEET UG Core",
        "Alcohols, Phenols & Ethers",
        r"\b(alcohols?|phenols?|ethers?|reimer[- ]tiemann|kolbe|williamson)\b|(?:ऐल्कोहॉल|एल्कोहॉल|फीनॉल|ईथर)",
        "Alcohols Phenols and Ethers Class 12",
        "Alcohol Phenol Ether Organic Chemistry",
    ),
    (
        70, "Chemistry", "Organic Chemistry", "Class 12", "Very High", "High-Yield NCERT",
        "Aldehydes, Ketones & Carboxylic Acids",
        r"\b(aldehydes?|ketones?|carboxylic|carbonyl|aldol|cannizzaro|clemmensen|wolff[- ]kishner)\b|(?:ऐल्डिहाइड|एल्डिहाइड|कीटोन|कार्बोक्सिलिक|ऐल्डॉल|कैनिज़ारो)",
        "Aldehydes Ketones and Carboxylic Acids",
        "Carbonyl Compounds Aldehyde Ketone",
    ),
    (
        71, "Chemistry", "Organic Chemistry", "Class 12", "High", "NEET UG Core",
        "Amines & Diazonium Salts",
        r"\b(amines?\b|diazonium|nitrogen containing organic|gabriel phthalimide|hoffmann bromamide|carbylamine)\b|(?:ऐमीन|एमीन|डाइएज़ोनियम)",
        "Amines Class 12 Chemistry",
        "Amines and Diazonium Salts Organic",
    ),
    (
        72, "Chemistry", "Organic Chemistry", "Class 12", "High", "NCERT Core",
        "Biomolecules & Practical Chemistry",
        r"\b(biomolecules?|carbohydrates?|glucose|amino acids|practical organic|\bpoc\b|practical chemistry|salt analysis)\b|(?:जैव[\s-]*अणु|कार्बोहाइड्रेट|ग्लूकोज|अमीनो\s*अम्ल|लवण\s*विश्लेषण)",
        "Biomolecules Class 12 Chemistry",
        "Practical Chemistry Salt Analysis POC",
    ),
]

TEACHER_PLAYLIST_SWEEPS: list[tuple[str, str]] = [
    # Physics Wallah / Competition Wallah / Yakeen / Prachand / Aarambh (Cached)
    ("Biology", "Competition Wallah NEET Biology"),
    ("Botany", "Competition Wallah Botany Tarun Sir Vipin Sir"),
    ("Zoology", "Competition Wallah Zoology Samapti Mam MD Sir"),
    ("Physics", "Competition Wallah NEET Physics MR Sir"),
    ("Chemistry", "Competition Wallah NEET Chemistry Pankaj Sir"),
    ("Biology", "Prachand NEET Biology"),
    ("Physics", "Prachand NEET Physics"),
    ("Chemistry", "Prachand NEET Chemistry"),
    ("Biology", "Aarambh NEET Biology"),
    ("Physics", "Aarambh NEET Physics"),
    ("Chemistry", "Aarambh NEET Chemistry"),
    ("Biology", "Yakeen NEET Biology"),
    ("Physics", "Yakeen NEET Physics"),
    ("Chemistry", "Yakeen NEET Chemistry"),
    # Top Individual NEET Educators (Cached)
    ("Biology", "Seep Pahuja NEET Biology"),
    ("Biology", "Garima Goel NEET Biology"),
    ("Biology", "Ritu Rattewal NEET Biology"),
    ("Botany", "Tarun Sir Botany NEET"),
    ("Biology", "Vipin Sharma Ozone Classes Biology NEET"),
    ("Biology", "KV Education NEET Biology"),
    ("Chemistry", "Nitesh Devnani NEET Chemistry"),
    ("Chemistry", "VT Sir NEET Chemistry"),
    ("Chemistry", "Pankaj Sir Chemistry NEET"),
    ("Physics", "Tamanna Chaudhary NEET Physics"),
    ("Physics", "MR Sir NEET Physics"),
    # Unacademy NEET, NEET Alchemy, Toppers (Cached)
    ("Biology", "Unacademy NEET Biology"),
    ("Physics", "Unacademy NEET Physics"),
    ("Chemistry", "Unacademy NEET Chemistry"),
    ("Biology", "NEET Alchemy Biology"),
    ("Chemistry", "NEET Alchemy Chemistry"),
    ("Physics", "NEET Alchemy Physics"),
    ("Biology", "Unacademy NEET Toppers Biology"),
    # ALLEN NEET, Aakash NEET, Vedantu NEET, Adda247, Sankalp, New Light, Biomentors, Motion, eSaral, Sri Chaitanya, Rankplus (Cached)
    ("Biology", "ALLEN NEET Biology"),
    ("Physics", "ALLEN NEET Physics"),
    ("Chemistry", "ALLEN NEET Chemistry"),
    ("Biology", "Aakash NEET Biology"),
    ("Physics", "Aakash NEET Physics"),
    ("Chemistry", "Aakash NEET Chemistry"),
    ("Biology", "Vedantu NEET Biology"),
    ("Physics", "Vedantu NEET Physics"),
    ("Chemistry", "Vedantu NEET Chemistry"),
    ("Biology", "NEET Adda247 Biology"),
    ("Chemistry", "NEET Adda247 Chemistry"),
    ("Physics", "NEET Adda247 Physics"),
    ("Biology", "Sankalp NEET Biology"),
    ("Biology", "Doctor Next NEET"),
    ("Biology", "New Light Institute NEET Biology"),
    ("Chemistry", "New Light Institute NEET Chemistry"),
    ("Biology", "Biomentors NEET Biology"),
    ("Physics", "Motion NEET Physics"),
    ("Chemistry", "Motion NEET Chemistry"),
    ("Physics", "eSaral NEET Physics"),
    ("Biology", "Sri Chaitanya Academy NEET"),
    ("Biology", "Infinity Learn NEET"),
    ("Biology", "Rankplus NEET"),

    # --- All-India Regional, Hindi Medium, Nursing & Class 12 PCB Board Playlist Sweeps ---
    ("Biology", "Biology Simplified Tamil NCERT"),
    ("Biology", "Vedantu Master Tamil NEET Biology"),
    ("Biology", "Xylem NEET Malayalam Biology"),
    ("Biology", "Eduport NEET Plus Two"),
    ("Biology", "Vedantu Telugu NEET Biology"),
    ("Physics", "SimplifiedMinds Karnataka 2nd PUC Physics"),
    ("Physics", "PW Kannada NEET KCET"),
    ("Chemistry", "BongMistry Class 12 Chemistry"),
    ("Biology", "PW Bangla NEET Biology"),
    ("Physics", "Physics Gyan Mukesh Nayak Class 12"),
    ("Chemistry", "Sovind Sir Chemistry Class 12"),
    ("Biology", "New Indian Era Class 12 Biology"),
    ("Chemistry", "Chemistry By NIMESHSIR"),
    ("Biology", "PW Gujarati NEET GUJCET"),
    ("Biology", "PW Odia NEET CHSE"),
    ("Biology", "PW Hindi Medium NEET Biology"),
    ("Biology", "Science Sangrah Class 12 Biology"),
    ("Physics", "Ashish Singh Lectures Class 12 Physics"),
    ("Biology", "Vijay Education BSc Nursing NEET"),
    ("Biology", "Sourabh Raina Class 12 Biology"),
    ("Chemistry", "Sourabh Raina Class 12 Chemistry"),
    ("Chemistry", "Bharat Panchal Class 12 Chemistry"),
    ("Physics", "Arvind Academy Class 12 Physics"),
    ("Biology", "NCERT Wallah Class 12 Biology"),
]

INSTITUTE_VIDEO_SWEEPS: list[tuple[str, str]] = [
    # Existing Pan-India NEET One-Shot Sweeps (Cached)
    ("Botany", "Competition Wallah Botany One Shot NEET"),
    ("Zoology", "Competition Wallah Zoology One Shot NEET"),
    ("Physics", "Competition Wallah Physics One Shot MR Sir NEET"),
    ("Chemistry", "Competition Wallah Chemistry One Shot NEET"),
    ("Biology", "Umeed NEET Biology One Shot Competition Wallah"),
    ("Physics", "Umeed NEET Physics One Shot Competition Wallah"),
    ("Chemistry", "Umeed NEET Chemistry One Shot Competition Wallah"),
    ("Biology", "Prachand NEET One Shot Biology"),
    ("Physics", "Prachand NEET One Shot Physics"),
    ("Chemistry", "Prachand NEET One Shot Chemistry"),
    ("Biology", "Seep Pahuja One Shot NEET Biology"),
    ("Biology", "Garima Goel One Shot NCERT NEET"),
    ("Biology", "Ritu Rattewal One Shot Biology NEET"),
    ("Biology", "Vipin Sharma NCERT One Shot NEET Biology"),
    ("Botany", "Tarun Sir One Shot Botany NEET"),
    ("Biology", "KV Education One Shot NEET Biology"),
    ("Chemistry", "Nitesh Devnani One Shot NEET Chemistry"),
    ("Chemistry", "VT Sir One Shot NEET Chemistry"),
    ("Chemistry", "Pankaj Sir Chemistry NEET One Shot"),
    ("Physics", "Tamanna Chaudhary One Shot NEET Physics"),
    ("Biology", "ALLEN NEET One Shot Biology"),
    ("Physics", "ALLEN NEET One Shot Physics"),
    ("Chemistry", "ALLEN NEET One Shot Chemistry"),
    ("Biology", "Aakash NEET One Shot Biology"),
    ("Physics", "Aakash NEET One Shot Physics"),
    ("Chemistry", "Aakash NEET One Shot Chemistry"),
    ("Biology", "Vedantu NEET One Shot Biology"),
    ("Physics", "Vedantu NEET One Shot Physics"),
    ("Chemistry", "Vedantu NEET One Shot Chemistry"),
    ("Biology", "NEET Adda247 One Shot Biology"),
    ("Chemistry", "NEET Adda247 One Shot Chemistry"),
    ("Physics", "NEET Adda247 One Shot Physics"),
    ("Biology", "Unacademy NEET One Shot Biology"),
    ("Physics", "Unacademy NEET One Shot Physics"),
    ("Chemistry", "Unacademy NEET One Shot Chemistry"),
    ("Biology", "New Light Institute NEET One Shot"),
    ("Biology", "Rankplus NEET One Shot"),
    ("Biology", "Infinity Learn NEET One Shot"),

    # --- Tamil NEET & Class 12 PCB ---
    ("Biology", "Biology Simplified Tamil NEET One Shot"),
    ("Biology", "Biology Simplified Tamil Class 12 One Shot"),
    ("Biology", "Vedantu Master Tamil NEET Biology One Shot"),
    ("Physics", "Vedantu Master Tamil NEET Physics One Shot"),
    ("Chemistry", "Vedantu Master Tamil NEET Chemistry One Shot"),
    ("Biology", "Xylem NEET Tamil Biology One Shot"),
    ("Physics", "Xylem NEET Tamil Physics One Shot"),
    ("Chemistry", "Xylem NEET Tamil Chemistry One Shot"),
    ("Biology", "PW Tamil NEET Biology One Shot"),
    ("Physics", "PW Tamil NEET Physics One Shot"),
    ("Chemistry", "PW Tamil NEET Chemistry One Shot"),

    # --- Malayalam NEET & Kerala Plus Two PCB ---
    ("Biology", "Xylem NEET Malayalam Biology One Shot"),
    ("Physics", "Xylem NEET Malayalam Physics One Shot"),
    ("Chemistry", "Xylem NEET Malayalam Chemistry One Shot"),
    ("Biology", "Xylem Plus Two Biology One Shot"),
    ("Physics", "Xylem Plus Two Physics One Shot"),
    ("Chemistry", "Xylem Plus Two Chemistry One Shot"),
    ("Biology", "Eduport NEET Plus Two Biology"),
    ("Physics", "Eduport Plus Two Physics"),
    ("Chemistry", "Eduport Plus Two Chemistry"),
    ("Biology", "Exam Winner Plus Two Biology"),
    ("Physics", "Exam Winner Plus Two Physics"),
    ("Chemistry", "Exam Winner Plus Two Chemistry"),

    # --- Telugu NEET & EAPCET / IPE PCB ---
    ("Biology", "Vedantu Telugu NEET Biology One Shot"),
    ("Physics", "Vedantu Telugu NEET Physics One Shot"),
    ("Chemistry", "Vedantu Telugu NEET Chemistry One Shot"),
    ("Physics", "Vedantu Telugu EAPCET Physics One Shot"),
    ("Chemistry", "Vedantu Telugu EAPCET Chemistry One Shot"),
    ("Biology", "PW Telugu NEET Biology One Shot"),
    ("Physics", "PW Telugu NEET Physics One Shot"),
    ("Chemistry", "PW Telugu NEET Chemistry One Shot"),

    # --- Kannada NEET, KCET & 2nd PUC PCB ---
    ("Biology", "PW Kannada NEET KCET Biology"),
    ("Physics", "PW Kannada NEET KCET Physics"),
    ("Chemistry", "PW Kannada NEET KCET Chemistry"),
    ("Biology", "SimplifiedMinds Karnataka Biology"),
    ("Physics", "SimplifiedMinds Karnataka Physics One Shot"),
    ("Chemistry", "SimplifiedMinds Karnataka Chemistry One Shot"),
    ("Physics", "EDUcare Karnataka 2nd PUC Physics"),

    # --- Bengali NEET, JENPAS & WBCHSE PCB ---
    ("Biology", "PW Bangla NEET Biology One Shot"),
    ("Physics", "PW Bangla NEET Physics One Shot"),
    ("Chemistry", "PW Bangla NEET Chemistry One Shot"),
    ("Chemistry", "BongMistry Chemistry One Shot"),
    ("Biology", "SOE Bangla Biology"),
    ("Physics", "SOE Bangla Physics One Shot"),
    ("Biology", "Biology Haters NEET One Shot"),
    ("Physics", "Science Beta Class 12 Physics"),

    # --- Marathi NEET, MHT-CET & HSC PCB ---
    ("Biology", "New Indian Era Biology One Shot"),
    ("Chemistry", "New Indian Era Chemistry One Shot"),
    ("Physics", "New Indian Era Physics One Shot"),
    ("Physics", "Physics Gyan Mukesh Nayak One Shot"),
    ("Chemistry", "Sovind Sir Chemistry One Shot"),
    ("Biology", "PW Maharashtra NEET MHT CET Biology"),
    ("Physics", "PW Maharashtra NEET MHT CET Physics"),
    ("Chemistry", "PW Maharashtra NEET MHT CET Chemistry"),
    ("Biology", "Giri Tutorials Class 12 Biology One Shot"),

    # --- Gujarati NEET, GUJCET & GSEB PCB ---
    ("Biology", "PW Gujarati NEET GUJCET Biology"),
    ("Physics", "PW Gujarati NEET GUJCET Physics"),
    ("Chemistry", "PW Gujarati NEET GUJCET Chemistry"),
    ("Biology", "PW Gujarat GSHSEB Biology One Shot"),
    ("Physics", "PW Gujarat GSHSEB Physics One Shot"),
    ("Chemistry", "PW Gujarat 11 12 Chemistry One Shot"),
    ("Chemistry", "Chemistry By NIMESHSIR One Shot"),
    ("Biology", "Vidyakul Gujarati Biology"),
    ("Physics", "Vidyakul Gujarati Std 12 Physics"),
    ("Biology", "Youth Vidyakul Std 12 Biology"),

    # --- Odia NEET & CHSE PCB ---
    ("Biology", "PW Odia NEET CHSE Biology"),
    ("Physics", "PW Odia NEET CHSE Physics"),
    ("Chemistry", "PW Odia NEET CHSE Chemistry"),
    ("Physics", "PW Odisha 11th 12th Physics One Shot"),
    ("Chemistry", "PW Odisha 11th 12th Chemistry One Shot"),
    ("Biology", "CHSE Catalyst Biology"),
    ("Physics", "CHSE Catalyst Physics"),
    ("Chemistry", "CHSE Catalyst Chemistry"),
    ("Physics", "MatSci Odia Physics"),

    # --- Punjabi & Pure English NEET ---
    ("Biology", "PW Punjabi Biology NEET"),
    ("Physics", "PW Punjabi Physics NEET"),
    ("Biology", "PW Punjab Board Biology"),
    ("Physics", "PW Punjab Board Physics"),
    ("Chemistry", "PW Punjab Board Chemistry"),
    ("Biology", "PW Punjab Board Class 12 Biology One Shot"),
    ("Physics", "PW Punjab Board Class 12 Physics One Shot"),
    ("Chemistry", "PW Punjab Board Class 12 Chemistry One Shot"),
    ("Biology", "Vedantu NEET English Biology One Shot"),
    ("Physics", "Vedantu NEET English Physics One Shot"),
    ("Chemistry", "Unacademy NEET English Chemistry One Shot"),
    ("Biology", "PW English NEET Biology One Shot"),

    # --- Hindi Medium & BSc Nursing / Paramedical ---
    ("Biology", "PW Hindi Medium NEET Biology One Shot"),
    ("Physics", "PW Hindi Medium NEET Physics One Shot"),
    ("Chemistry", "PW Hindi Medium NEET Chemistry One Shot"),
    ("Biology", "Science Sangrah Biology One Shot"),
    ("Chemistry", "Science Sangrah Chemistry One Shot"),
    ("Physics", "Science Sangrah Physics One Shot"),
    ("Physics", "Ashish Singh Lectures Physics One Shot"),
    ("Chemistry", "Ashish Singh Lectures Chemistry One Shot"),
    ("Biology", "Ashish Singh Lectures NEET Biology One Shot"),
    ("Physics", "Learn and Share Class 12 Physics One Shot"),
    ("Chemistry", "Learn and Share Class 12 Chemistry One Shot"),
    ("Biology", "Doubtnut NEET Hindi Biology One Shot"),
    ("Biology", "Vijay Education BSc Nursing NEET Biology"),
    ("Chemistry", "Vijay Education BSc Nursing Chemistry"),
    ("Physics", "Vijay Education BSc Nursing Physics"),

    # --- Famous Class 12 PCB Boards & AIIMS One-Shots ---
    ("Biology", "Sourabh Raina Class 12 Biology One Shot"),
    ("Chemistry", "Sourabh Raina Class 12 Chemistry One Shot"),
    ("Chemistry", "Bharat Panchal Class 12 Chemistry One Shot"),
    ("Physics", "Arvind Academy Class 12 Physics One Shot"),
    ("Physics", "Munil Sir Class 12 Physics One Shot"),
    ("Physics", "Science and Fun Class 12 Physics One Shot"),
    ("Chemistry", "Science and Fun Class 12 Chemistry One Shot"),
    ("Biology", "Science and Fun Class 12 Biology One Shot"),
    ("Biology", "NCERT Wallah Class 12 Biology One Shot"),
    ("Physics", "NCERT Wallah Vijeta Class 12 Physics One Shot"),
    ("Chemistry", "NCERT Wallah Vijeta Class 12 Chemistry One Shot"),
    ("Biology", "LearnoHub Class 12 Biology One Shot"),
    ("Biology", "AIIMS NEET Biology Assertion Reason One Shot"),
    ("Physics", "AIIMS NEET Physics Rank Booster One Shot"),
]

# Curated Allowlist of Legitimate NEET UG, Regional, Nursing & PCB Board Channels
VERIFIED_CHANNEL_PATTERNS = (
    # Pan-India NEET Core
    "competition wallah",
    "yakeen",
    "physics wallah",
    "lakshya neet",
    "arjuna neet",
    "pw neet",
    "neet pw",
    "pw class 11",
    "pw class 12",
    "pw english",
    "pw vidyapeeth",
    "pw power prep",
    "pw test series",
    "neet wallah",
    "ncert wallah",
    "vijeta",
    "prachand",
    "aarambh",
    "unacademy neet",
    "neet alchemy",
    "neet achievers by unacademy",
    "unacademy sapiens",
    "akansha karnwal unacademy",
    "unacademy neet toppers",
    "let's crack neet",
    "allen neet",
    "allen career institute",
    "allen digital",
    "allen online",
    "aakash neet",
    "aakash institute",
    "neet@aakash",
    "aakash byju",
    "byju's neet",
    "byjus neet",
    "vedantu neet",
    "vedantu biotonic",
    "neet adda247",
    "adda247 neet",
    "doctors adda",
    "garima goel",
    "seep pahuja",
    "tarun sir",
    "ritu rattewal",
    "vipin sharma",
    "ozone classes",
    "kv education",
    "nitesh devnani",
    "tamanna chaudhary",
    "sankalp",
    "doctor next",
    "new light institute",
    "new light neet",
    "new light prayaas",
    "biomentors",
    "esaral",
    "motion neet",
    "motion education",
    "sri chaitanya academy neet",
    "infinity learn neet",
    "neet infinity learn",
    "infinity learn",
    "rankplus",
    "pankaj sir chemistry",
    "vt sir",
    "vishal tiwari",
    "mr sir",
    "khan academy india",

    # Tamil
    "biology simplified tamil",
    "senthilnathan",
    "vedantu master tamil",
    "vedantu neet tamil",
    "v neet tamil",
    "state board neet tamil",
    "pw tamil",
    "physics wallah tamil",
    "nalamudan",

    # Malayalam
    "xylem",
    "eduport",
    "exam winner",
    "brilliant pala",
    "pw malayalam",
    "physics wallah malayalam",
    "vedantu plus one",

    # Telugu
    "vedantu telugu",
    "pw telugu",
    "physics wallah telugu",
    "unacademy telugu",
    "unacademy neet telugu",

    # Kannada
    "simplifiedminds",
    "simplified minds",
    "educare karnataka",
    "pw kannada",
    "pw kcet",
    "physics wallah kannada",
    "parikshe",
    "vedantu karnataka",

    # Bengali
    "pw bangla",
    "physics wallah bangla",
    "bongmistry",
    "bong mistry",
    "soe bangla",
    "biology haters",
    "science beta",
    "unacademy bangla",

    # Marathi
    "physics gyan",
    "mukesh nayak",
    "sovind sir",
    "all about chemistry",
    "new indian era",
    "dinesh sir",
    "shubham muley",
    "giri tutorials",
    "pradeep giri 11th",
    "pawan wagh",
    "pw maharashtra",
    "pw mht cet",
    "physics wallah maharashtra",

    # Gujarati
    "pw gujarati",
    "pw gujarat",
    "gshseb",
    "physics wallah gujarati",
    "vidyakul",
    "youth education",
    "diwalipura",
    "nimeshsir",
    "nimesh sir",

    # Odia & Punjabi
    "pw odia",
    "pw odisha",
    "physics wallah odia",
    "chse catalyst",
    "vidyant chse",
    "matsci odia",
    "matsci science",
    "pw punjabi",
    "pw punjab",
    "physics wallah punjabi",

    # Hindi Medium, BSc Nursing & Class 12 PCB Boards
    "pw hindi",
    "physics wallah hindi",
    "neet hindi",
    "ashish singh lectures",
    "learn and share",
    "science sangrah",
    "anu sir bihar board",
    "doubtnut",
    "utkarsh",
    "sourabh raina",
    "bharat panchal",
    "chemistry guruji",
    "arvind academy",
    "munil sir",
    "science and fun",
    "ashu ghai 11th",
    "next toppers - 12th science",
    "class 12 by unacademy",
    "learnohub",
    "magnet brains",
    "bsc nursing",
    "adda247 nursing",
    "vijay education",
    "anand mani",
)
VERIFIED_CHANNEL_SUBSTRINGS = VERIFIED_CHANNEL_PATTERNS

# Reject fan-clip channels, shorts aggregators, MBBS/PG/NORCET channels, Class 6-10 subchannels, and JEE-only channels
CHANNEL_DISQUALIFY_RE = re.compile(
    r"\b(fan\s*page|fan\s*club|fans\b|pupils|disciples|emotion|moments|clips|shorts|"
    r"goats\s+of|shayari|comedy|parody|roast|yakeenian\w*|pwian\w*|unofficial|tribute|status|edits|"
    r"vibes|army|lovers|meded|neet\s*pg|fmge|ini\s*cet|usmle|norcet|nursing\s*officer|utkarsh\s*nursing|"
    r"counselling|ayush|"
    r"jee\s*wallah|lakshya\s*jee|arjuna\s*jee|pw\s*jee|jee\s*challengers|"
    r"allen\s*jee|unacademy\s*jee|unacademy\s*atoms|jee\s*nexus|jeefinity|jee\s*legends|jee\s*alchemy|"
    r"aakash\s*jee|jee@aakash|byju'?s\s*jee|vedantu\s*jee|motion\s*jee|vmc\s*jee|"
    r"xylem\s*jee|eduport\s*jee|exam\s*winner\s*jee|"
    r"sri\s*chaitanya\s*academy\s*jee|infinity\s*learn\s*jee|rankers\s*jee|"
    r"mathongo|jeeongo|eduniti|mohit\s*tyagi|competishun|mathsmerizing|"
    r"pw\s*foundation|neet\s*foundation|udaan|neev|sslc|class\s*(?:6|7|8|9|10)\b(?!.*(?:neet|11|12))|"
    r"commerce\s*wallah|arts\s*wallah|gate\s*wallah|"
    r"ssc\s*wallah|upsc\s*wallah|banking\s*wallah|defence\s*wallah|cuet\s*wallah|"
    r"law\s*wallah|ca\s*wallah|teaching\s*wallah|sankalp\s*ssc|sankalp\s*civil|"
    r"ssc\s*utkarsh|upsc\s*utkarsh|agriculture)\b",
    re.I,
)

# Strict Title Rejections: JEE-Advanced-only, Class 6/7/8/9/10, SSC/Railway/UPSC, and Non-lecture noise
# NOTE: Regional languages & State Medical/PCB CETs (KCET, MHT-CET, EAPCET, KEAM, GUJCET, JENPAS) are PERMITTED!
HARD_REJECT_RE = re.compile(
    r"\b(jee\s*adv\w*|iit\s+jee\s+maths|irodov|pathfinder|mathongo|jeeongo|black\s*book|cengage\s*jee|josaa|"
    r"bitsat|comedk|viteee|neet\s*pg|fmge|ini\s*cet|norcet|nursing\s*officer|mbbs\s*1st\s*year|"
    r"class\s*(?:6|7|8|9|10|ix|x)\b|std\s*(?:6|7|8|9|10)\b|dhoran\s*(?:6|7|8|9|10)\b|"
    r"sslc|madhyamik|icse|ssc\s+cgl|ssc\s+chsl|ssc\s+gd|ssc\s+board|railway\s+exam|rrb\s+ntpc|upsc|tgt|pgt|dsssb|kvs|cuet\s+only|"
    r"vlog\w*|prank|controversy|exposed|roast|reaction\s+video|"
    r"cutoff|cut[\s-]*off|marks\s+vs\s+rank|rank\s+vs\s+college|safe\s+score|"
    r"college\s+review|campus\s+tour|hostel\s+tour|medical\s+college\s+life|"
    r"counselling|mcc\s+counselling|choice\s+filling|seat\s+matrix|"
    r"dress\s+code|admit\s+card|omr\s+sheet|city\s+intimation|application\s+form|registration\s+process|"
    r"supreme\s+court|re[\s-]*neet\s+(?:news|update|protest|scam|verdict|hearing)|paper\s+leak|nta\s+latest|nta\s+official\s+update|"
    r"answer\s+key|paper\s+discussion|paper\s+analysis|paper\s+solutions?|question\s+paper\s+solutions?|"
    r"video\s+solutions|memory\s+based|"
    r"toppers?\s+talk|topper'?s?\s+interview|toppers?\s+interview|topper\s+podcast|podcast\s+with|"
    r"topper'?s?\s+success|success\s+story|success\s+meet|full\s+interview|air\s*1\s+interview|"
    r"result\s+reaction|result\s+celebration|orientation\s+session|study\s+material\s+review|"
    r"time\s*table|how\s+to\s+crack|strategy\s+to\s+score|strategy\s+for\s+neet|"
    r"best\s+books\s+for|motivation|motivational|shorts|#shorts)\b"
    r"|(?:कक्षा\s*(?:6|7|8|9|10)\b|ધોરણ\s*(?:6|7|8|9|10|૯|૧૦)|মাধ্যমিক)"
    r"|(?<!11th\s)(?<!12th\s)\b(?:6th|7th|8th|9th|10th)\s+(?:class|std|standard|science|board)\b",
    re.I,
)


def parse_views(text: str) -> int:
    if not text:
        return 0
    cleaned = text.lower().replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*([kmb]|lakh|cr)?", cleaned)
    if not m:
        return 0
    val = float(m.group(1))
    mult = m.group(2) or ""
    if mult == "k":
        val *= 1_000
    elif mult == "m":
        val *= 1_000_000
    elif mult == "b":
        val *= 1_000_000_000
    elif mult == "lakh":
        val *= 100_000
    elif mult == "cr":
        val *= 10_000_000
    return int(val)


def parse_duration_seconds(text: str) -> int:
    if not text:
        return 0
    parts = [int(p) for p in re.findall(r"\d+", text)]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return 0


def parse_lesson_count(text: str) -> int:
    if not text:
        return 0
    m = re.search(r"(\d+)", text.replace(",", ""))
    return int(m.group(1)) if m else 0


def search_youtube(query: str, params: str = "", use_cache: bool = True) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_id = f"{query}::sp={params}" if params else query
    key = hashlib.sha1(cache_id.encode("utf-8")).hexdigest()
    cpath = CACHE_DIR / f"{key}.json"
    if use_cache and cpath.exists():
        with _lock:
            STATS["cached"] += 1
        return json.loads(cpath.read_text(encoding="utf-8"))

    body: dict = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20250101.00.00",
                "hl": "en",
                "gl": "IN",
            }
        },
        "query": query,
    }
    if params:
        body["params"] = params
    payload = json.dumps(body).encode("utf-8")

    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                INNERTUBE_SEARCH,
                data=payload,
                headers={"User-Agent": UA, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
                data = json.load(resp)
            with _lock:
                STATS["requests"] += 1
            cpath.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.7 * (attempt + 1))
    print(f"WARN: search failed for {query!r}: {last_err}", flush=True)
    return {}


def extract_candidates(payload: dict) -> list[dict]:
    items = []
    try:
        sections = (
            payload["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]
            ["sectionListRenderer"]["contents"]
        )
    except (KeyError, TypeError):
        return items

    for sec in sections:
        contents = sec.get("itemSectionRenderer", {}).get("contents", [])
        for entry in contents:
            if "lockupViewModel" in entry:
                parsed = _parse_lockup(entry["lockupViewModel"])
                if parsed:
                    items.append(parsed)
            elif "playlistRenderer" in entry:
                parsed = _parse_legacy_playlist(entry["playlistRenderer"])
                if parsed:
                    items.append(parsed)
            elif "videoRenderer" in entry:
                parsed = _parse_video(entry["videoRenderer"])
                if parsed:
                    items.append(parsed)
    return items


def _parse_lockup(lv: dict) -> dict | None:
    cid = (lv.get("contentId") or "").strip()
    ctype = lv.get("contentType") or ""
    if not cid or ("PLAYLIST" not in ctype and "COURSE" not in ctype and not cid.startswith("PL")):
        return None
    if cid.startswith("RD"):
        return None

    meta_vm = lv.get("metadata", {}).get("lockupMetadataViewModel", {})
    title = (meta_vm.get("title", {}).get("content") or "").strip()
    if not title:
        return None

    rows = (
        meta_vm.get("metadata", {})
        .get("contentMetadataViewModel", {})
        .get("metadataRows", [])
    )
    channel = ""
    channel_url = ""
    sample_lectures: list[dict] = []

    for row in rows:
        parts = row.get("metadataParts") or []
        for part in parts:
            txt_obj = part.get("text") or {}
            content = (txt_obj.get("content") or "").strip()
            if not content or content.lower() in {"playlist", "course", "view full playlist", "view full course", "podcast"}:
                continue
            cmd_runs = txt_obj.get("commandRuns") or []
            web_url = ""
            watch_vid = ""
            if cmd_runs:
                icmd = cmd_runs[0].get("onTap", {}).get("innertubeCommand", {})
                web_url = icmd.get("commandMetadata", {}).get("webCommandMetadata", {}).get("url") or ""
                watch_vid = icmd.get("watchEndpoint", {}).get("videoId") or ""

            if not channel and (web_url.startswith("/@") or web_url.startswith("/channel/") or web_url.startswith("/c/")):
                channel = content
                channel_url = f"https://www.youtube.com{web_url}"
            elif watch_vid and len(sample_lectures) < 4:
                sample_lectures.append(
                    {
                        "video_id": watch_vid,
                        "title": content,
                        "url": f"https://www.youtube.com/watch?v={watch_vid}&list={cid}",
                    }
                )

    if not channel and rows:
        first_parts = rows[0].get("metadataParts") or []
        if first_parts:
            channel = (first_parts[0].get("text", {}).get("content") or "").strip()

    thumb_vm = (
        lv.get("contentImage", {})
        .get("collectionThumbnailViewModel", {})
        .get("primaryThumbnail", {})
        .get("thumbnailViewModel", {})
    )
    sources = thumb_vm.get("image", {}).get("sources") or []
    thumbnail = sources[-1]["url"] if sources else ""

    lesson_count = 0
    for ov in thumb_vm.get("overlays") or []:
        badges = ov.get("thumbnailOverlayBadgeViewModel", {}).get("thumbnailBadges") or []
        for b in badges:
            btxt = b.get("thumbnailBadgeViewModel", {}).get("text") or ""
            cnt = parse_lesson_count(btxt)
            if cnt:
                lesson_count = cnt
                break

    embed_vid = sample_lectures[0]["video_id"] if sample_lectures else ""
    if not embed_vid and thumbnail:
        m = re.search(r"/vi/([A-Za-z0-9_-]{11})/", thumbnail)
        if m:
            embed_vid = m.group(1)

    return {
        "provider": "playlist",
        "video_id": cid,
        "embed_video_id": embed_vid,
        "url": f"https://www.youtube.com/playlist?list={cid}",
        "title": title,
        "channel": channel or "NEET UG Faculty",
        "channel_url": channel_url,
        "thumbnail": thumbnail,
        "lesson_count": lesson_count,
        "duration": "",
        "duration_sec": 0,
        "views_text": "",
        "view_count": 0,
        "published": "",
        "sample_lectures": sample_lectures,
    }


def _parse_legacy_playlist(pr: dict) -> dict | None:
    cid = (pr.get("playlistId") or "").strip()
    title = (pr.get("title", {}).get("simpleText") or "").strip()
    if not cid or not title or cid.startswith("RD"):
        return None
    runs = pr.get("shortBylineText", {}).get("runs") or pr.get("longBylineText", {}).get("runs") or []
    channel = (runs[0].get("text") if runs else "").strip() or "NEET UG Faculty"
    thumbs = pr.get("thumbnails", [{}])[0].get("thumbnails") or []
    thumbnail = thumbs[-1].get("url", "") if thumbs else ""
    embed_vid = ""
    if thumbnail:
        m = re.search(r"/vi/([A-Za-z0-9_-]{11})/", thumbnail)
        if m:
            embed_vid = m.group(1)
    lesson_count = parse_lesson_count(pr.get("videoCount") or "")
    return {
        "provider": "playlist",
        "video_id": cid,
        "embed_video_id": embed_vid,
        "url": f"https://www.youtube.com/playlist?list={cid}",
        "title": title,
        "channel": channel,
        "channel_url": "",
        "thumbnail": thumbnail,
        "lesson_count": lesson_count,
        "duration": "",
        "duration_sec": 0,
        "views_text": "",
        "view_count": 0,
        "published": "",
        "sample_lectures": [],
    }


def _parse_video(vr: dict) -> dict | None:
    vid = (vr.get("videoId") or "").strip()
    runs = vr.get("title", {}).get("runs") or []
    title = "".join(r.get("text", "") for r in runs).strip()
    if not vid or not title or len(vid) != 11:
        return None

    owner_runs = vr.get("ownerText", {}).get("runs") or vr.get("longBylineText", {}).get("runs") or []
    channel = (owner_runs[0].get("text") if owner_runs else "").strip() or "NEET UG Faculty"
    channel_url = ""
    if owner_runs:
        wurl = (
            owner_runs[0]
            .get("navigationEndpoint", {})
            .get("commandMetadata", {})
            .get("webCommandMetadata", {})
            .get("url")
            or ""
        )
        if wurl:
            channel_url = f"https://www.youtube.com{wurl}"

    length_text = (vr.get("lengthText", {}).get("simpleText") or "").strip()
    dur_sec = parse_duration_seconds(length_text)

    views_text = (vr.get("viewCountText", {}).get("simpleText") or "").strip()
    view_count = parse_views(views_text)
    published = (vr.get("publishedTimeText", {}).get("simpleText") or "").strip()

    thumbs = vr.get("thumbnail", {}).get("thumbnails") or []
    thumbnail = thumbs[-1].get("url", "") if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

    return {
        "provider": "youtube",
        "video_id": vid,
        "embed_video_id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": title,
        "channel": channel,
        "channel_url": channel_url,
        "thumbnail": thumbnail,
        "lesson_count": 0,
        "duration": length_text,
        "duration_sec": dur_sec,
        "views_text": views_text,
        "view_count": view_count,
        "published": published,
        "sample_lectures": [],
    }


def is_verified_neet_channel(channel: str) -> bool:
    if not channel:
        return False
    low = channel.casefold().strip()
    if CHANNEL_DISQUALIFY_RE.search(low):
        return False
    # Reject JEE-only channels while permitting multi-exam channels that include NEET/Medical/CET/Boards/Regional
    if re.search(r"\b(jee|iit)\b", low) and not re.search(
        r"\b(neet|medical|biology|cet|kcet|eapcet|eamcet|gujcet|board|tamil|telugu|kannada|malayalam|bangla|maharashtra|gujarati|odia|utkarsh|doubtnut|ashish|vidyakul)\b",
        low,
    ):
        return False
    if any(sub in low for sub in VERIFIED_CHANNEL_PATTERNS):
        return True
    return False


def resolve_institute(cand: dict) -> str:
    ch_low = cand["channel"].lower()
    if any(
        k in ch_low
        for k in (
            "competition wallah",
            "yakeen",
            "physics wallah",
            "lakshya neet",
            "arjuna neet",
            "pw neet",
            "neet pw",
            "pw class 11",
            "pw class 12",
            "pw english",
            "pw vidyapeeth",
            "pw power prep",
            "pw test series",
            "neet wallah",
            "ncert wallah",
            "vijeta",
            "prachand",
            "aarambh",
            "pw tamil",
            "pw malayalam",
            "pw telugu",
            "pw kannada",
            "pw kcet",
            "pw bangla",
            "pw maharashtra",
            "pw mht cet",
            "pw gujarati",
            "pw gujarat",
            "pw odia",
            "pw odisha",
            "pw punjabi",
            "pw punjab",
            "pw hindi",
            "neet hindi",
        )
    ):
        return "Physics Wallah (PW)"
    if any(k in ch_low for k in ("unacademy", "neet alchemy", "let's crack neet")):
        return "Unacademy NEET"
    if "allen" in ch_low:
        return "ALLEN NEET"
    if "aakash" in ch_low or "byju" in ch_low:
        return "Aakash & BYJU'S NEET"
    if "vedantu" in ch_low:
        return "Vedantu NEET"
    if any(k in ch_low for k in ("xylem", "eduport", "exam winner", "brilliant pala")):
        return "Xylem, Eduport & Kerala NEET"
    if any(k in ch_low for k in ("adda247", "doctors adda", "sankalp", "doctor next")):
        return "Adda247 & Sankalp NEET"
    if "new light" in ch_low or "biomentors" in ch_low:
        return "New Light & Biomentors"
    if "sri chaitanya" in ch_low or "infinity learn" in ch_low:
        return "Sri Chaitanya & Infinity Learn"
    if any(k in ch_low for k in ("motion", "esaral", "rankplus")):
        return "Motion, eSaral & Rankplus"
    if any(
        k in ch_low
        for k in (
            "sourabh raina",
            "bharat panchal",
            "chemistry guruji",
            "arvind academy",
            "munil sir",
            "science and fun",
            "learnohub",
            "magnet brains",
            "ashish singh",
            "learn and share",
            "science sangrah",
            "doubtnut",
            "utkarsh",
            "vijay education",
            "bsc nursing",
        )
    ):
        return "CBSE, Hindi Medium & Nursing"
    if any(
        k in ch_low
        for k in (
            "biology simplified tamil",
            "senthilnathan",
            "nalamudan",
            "simplifiedminds",
            "simplified minds",
            "educare karnataka",
            "parikshe",
            "bongmistry",
            "bong mistry",
            "soe bangla",
            "biology haters",
            "science beta",
            "physics gyan",
            "mukesh nayak",
            "sovind sir",
            "all about chemistry",
            "new indian era",
            "dinesh sir",
            "shubham muley",
            "giri tutorials",
            "pawan wagh",
            "vidyakul",
            "youth education",
            "diwalipura",
            "nimeshsir",
            "nimesh sir",
            "chse catalyst",
            "matsci odia",
        )
    ):
        return "All-India Regional NEET & CET"
    return "Independent NEET Specialists"


def resolve_educator(cand: dict, subject: str, unit: str) -> str:
    blob = f"{cand['title']} {cand['channel']}".lower()

    teacher_rules = [
        # Named Pan-India NEET Specialists
        (r"\bmr\s*sir\b|\bmanish\s*raj\b", "MR Sir (Manish Raj)"),
        (r"\btarun\s*sir\b|\btarun\s*kumar\b", "Tarun Sir (Botany)"),
        (r"\bseep\s*pahuja\b", "Seep Pahuja Ma'am"),
        (r"\bgarima\s*goel\b", "Garima Goel Ma'am"),
        (r"\britu\s*rattewal\b", "Ritu Rattewal Ma'am"),
        (r"\bvipin\s*(?:kumar\s*)?sharma\b|ozone\s*classes", "Vipin Sharma (Ozone Classes)"),
        (r"kv\s*education", "KV Education"),
        (r"\bnitesh\s*devnani\b", "Nitesh Devnani Sir"),
        (r"\btamanna\s*chaudhary\b", "Tamanna Chaudhary Ma'am"),
        (r"\bpankaj\s*sir\b|\bpankaj\s*sijairya\b", "Pankaj Sir Chemistry"),
        (r"\bvt\s*sir\b|\bvishal\s*tiwari\b", "VT Sir (Vishal Tiwari)"),
        (r"\bsamapti\s*(?:sinha\s*)?(?:ma'?am|mahapatra)?\b", "Samapti Sinha Ma'am"),
        (r"\bmanish\s*dubey\b|\bmd\s*sir\b", "MD Sir (Manish Dubey)"),
        (r"\brupesh\s*chaudhary\b|\brupesh\s*sir\b", "Rupesh Chaudhary Sir"),
        (r"\bakanksha\s*agarwal\b|\bguru\s*maa\b", "Akanksha Agarwal Ma'am"),
        (r"\bakansha\s*karnwal\b", "Akansha Karnwal Ma'am"),
        (r"\bsudhanshu\s*(?:tak\s*)?sir\b|\bsudhanshu\s*tak\b", "Sudhanshu Sir"),
        (r"\bamit\s*mahajan\b", "Amit Mahajan Sir"),
        (r"\byogesh\s*jain\b", "Yogesh Jain Sir"),
        (r"\bmohit\s*dadheech\b", "Mohit Dadheech Sir"),
        (r"\bhitesh\s*sopra\b", "Hitesh Sopra Sir"),
        (r"\bayudh\s*(?:yashlaha\s*)?sir\b|\bayudh\s*yashlaha\b", "Ayudh Yashlaha Sir"),
        (r"\bprateek\s*jain\b", "Prateek Jain Sir"),
        (r"\bmahendra\s*singh\b", "Mahendra Singh Sir"),
        (r"\banupam\s*upadhyay\b", "Anupam Upadhyay Sir"),
        (r"\bwassim\s*bhat\b", "Wassim Bhat Sir"),
        (r"\bvani\s*sood\b|\bvani\s*ma'?am\b|vedantu\s*biotonic", "Vani Ma'am (Vedantu)"),
        (r"\bgargi\s*singh\b", "Dr. Gargi Singh"),
        (r"\bambika\s*(?:sharma|ma'?am)\b", "Ambika Ma'am"),
        (r"\balakh\s*pandey\b|physics\s*wallah\s*-\s*alakh", "Alakh Pandey Sir"),
        (r"\bgeetendra\b|biomentors", "Dr. Geetendra (Biomentors)"),

        # Named Regional, Board & Nursing Educators
        (r"biology\s*simplified\s*tamil|senthilnathan", "Senthilnathan Sir (Biology Simplified Tamil)"),
        (r"vedantu\s*master\s*tamil|vedantu\s*neet\s*tamil|v\s*neet\s*tamil|state\s*board\s*neet\s*tamil", "Vedantu Master Tamil"),
        (r"xylem.*tamil", "Xylem NEET Tamil"),
        (r"pw\s*tamil|physics\s*wallah\s*tamil", "PW Tamil"),
        (r"xylem\s*neet|xylem\s*plus|xylem\s*learning|\bxylem\b", "Xylem Learning (Kerala)"),
        (r"eduport", "Eduport (Kerala)"),
        (r"exam\s*winner", "Exam Winner (Kerala)"),
        (r"brilliant\s*pala", "Brilliant Study Centre Pala"),
        (r"pw\s*malayalam|physics\s*wallah\s*malayalam", "PW Malayalam"),
        (r"vedantu\s*plus\s*one", "Vedantu Malayalam"),
        (r"vedantu\s*telugu", "Vedantu Telugu"),
        (r"pw\s*telugu|physics\s*wallah\s*telugu", "PW Telugu"),
        (r"unacademy.*telugu", "Unacademy NEET Telugu"),
        (r"simplified\s*minds", "SimplifiedMinds Karnataka"),
        (r"educare\s*karnataka", "EDUcare Karnataka"),
        (r"pw\s*kannada|pw\s*kcet|physics\s*wallah\s*kannada", "PW Kannada"),
        (r"parikshe", "PARIKSHE Karnataka"),
        (r"vedantu\s*karnataka", "Vedantu Karnataka"),
        (r"bong\s*mistry", "BongMistry (Subhajit Sir)"),
        (r"soe\s*bangla", "SOE Bangla"),
        (r"biology\s*haters", "Biology Haters (Bangla)"),
        (r"science\s*beta", "Science Beta (Bangla)"),
        (r"pw\s*bangla|physics\s*wallah\s*bangla", "PW Bangla"),
        (r"unacademy\s*bangla", "Unacademy Bangla"),
        (r"physics\s*gyan|mukesh\s*nayak", "Mukesh Nayak Sir (Physics Gyan)"),
        (r"sovind\s*sir|all\s*about\s*chemistry", "Sovind Sir (All About Chemistry)"),
        (r"new\s*indian\s*era", "New Indian Era (Prashant Sir)"),
        (r"giri\s*tutorials|pradeep\s*giri", "Giri Tutorials (Pradeep Giri)"),
        (r"pawan\s*wagh", "Pawan Wagh Academy"),
        (r"pw\s*maharashtra|pw\s*mht\s*cet|physics\s*wallah\s*maharashtra", "PW Maharashtra"),
        (r"nimesh\s*sir", "Chemistry By NIMESHSIR"),
        (r"pw\s*gujarat\w*|gshseb|physics\s*wallah\s*gujarati", "PW Gujarati"),
        (r"vidyakul\s*gujarati|youth\s*vidyakul|youth\s*education", "Vidyakul Gujarati"),
        (r"diwalipura", "The Diwalipura Youth"),
        (r"pw\s*odia|pw\s*odisha|physics\s*wallah\s*odia", "PW Odia"),
        (r"chse\s*catalyst|vidyant\s*chse", "CHSE Catalyst (Odia)"),
        (r"matsci\s*odia|matsci\s*science", "MatSci Odia"),
        (r"pw\s*punjabi|pw\s*punjab|pw\s*vidyapeeth\s*punjab|physics\s*wallah\s*punjabi", "PW Punjab"),
        (r"pw\s*hindi|physics\s*wallah\s*hindi|neet\s*hindi", "PW Hindi Medium"),
        (r"science\s*sangrah|anu\s*sir\s*bihar\s*board", "Science Sangrah (Anu Sir)"),
        (r"ashish\s*singh\s*lectures", "Ashish Singh Lectures"),
        (r"learn\s*and\s*share", "Learn and Share"),
        (r"vijay\s*education|adda247\s*nursing", "Vijay Education (BSc Nursing)"),
        (r"anand\s*mani", "Dr. Anand Mani"),
        (r"sourabh\s*raina", "Sourabh Raina Sir"),
        (r"bharat\s*panchal|chemistry\s*guruji", "Bharat Panchal (Chemistry Guruji)"),
        (r"arvind\s*academy", "Arvind Academy"),
        (r"munil\s*sir", "Munil Sir Physics"),
        (r"science\s*and\s*fun|\bashu\s*ghai\b|next\s*toppers.*12th", "Science and Fun (Ashu Sir)"),
        (r"learnohub", "LearnoHub"),
        (r"magnet\s*brains", "Magnet Brains"),
        (r"doubtnut", "Doubtnut"),
        (r"utkarsh", "Utkarsh NEET & Boards"),
        (r"vedantu\s*neet\s*english", "Vedantu NEET English"),
        (r"unacademy\s*neet\s*english", "Unacademy NEET English"),
        (r"pw\s*english", "PW English"),
        (r"ncert\s*wallah|vijeta", "NCERT Wallah (PW)"),

        # Institute Umbrellas
        (r"new\s*light\s*institute|new\s*light\s*neet|\bs\.?\s*p\.?\s*singh\b", "New Light Institute"),
        (r"allen\s*neet|allen\s*career|allen\s*digital|allen\s*online", "ALLEN NEET"),
        (r"aakash.*byju|byju.*neet", "Aakash BYJU'S NEET"),
        (r"aakash\s*neet|neet@aakash", "Aakash NEET"),
        (r"sri\s*chaitanya|infinity\s*learn", "Sri Chaitanya / Infinity Learn NEET"),
        (r"motion\s*neet|motion\s*education", "Motion NEET Kota"),
        (r"esaral", "eSaral NEET"),
        (r"neet\s*adda247|adda247\s*neet|doctors\s*adda", "NEET Adda247"),
        (r"doctor\s*next", "Doctor Next"),
        (r"sankalp", "Sankalp NEET"),
        (r"rankplus", "Rankplus NEET"),
        (r"unacademy\s*neet\s*toppers", "Unacademy NEET Toppers"),
        (r"neet\s*alchemy", "NEET Alchemy (Unacademy)"),
        (r"unacademy\s*neet", "Unacademy NEET"),
        (r"vedantu\s*neet", "Vedantu NEET"),
        (r"yakeen", "PW Yakeen"),
        (r"competition\s*wallah", "Competition Wallah (PW)"),
    ]
    for pat, label in teacher_rules:
        if re.search(pat, blob):
            return label

    return cand["channel"]


def resolve_language(cand: dict) -> str:
    """Return ONLY one of the 12 exact canonical language strings."""
    raw = f"{cand['title']} {cand['channel']}"
    blob = raw.lower()

    # 1. Tamil (checked before Malayalam so 'Xylem NEET Tamil' -> 'Tamil')
    if (
        re.search(r"[\u0B80-\u0BFF]", raw)
        or re.search(
            r"\btamil\b|தமிழ்|biology\s*simplified\s*tamil|senthilnathan|"
            r"vedantu\s*master\s*tamil|vedantu\s*neet\s*tamil|xylem.*tamil|"
            r"pw\s*tamil|physics\s*wallah\s*tamil|nalamudan",
            blob,
        )
    ):
        return "Tamil"

    # 2. Telugu
    if (
        re.search(r"[\u0C00-\u0C7F]", raw)
        or re.search(
            r"\btelugu\b|తెలుగు|vedantu\s*telugu|pw\s*telugu|physics\s*wallah\s*telugu|"
            r"unacademy.*telugu|\bkiran\s*sir\b",
            blob,
        )
    ):
        return "Telugu"

    # 3. Kannada
    if (
        re.search(r"[\u0C80-\u0CFF]", raw)
        or re.search(
            r"\bkannada\b|ಕನ್ನಡ|simplified\s*minds|educare\s*karnataka|"
            r"pw\s*kannada|pw\s*kcet|physics\s*wallah\s*kannada|parikshe|vedantu\s*karnataka",
            blob,
        )
    ):
        return "Kannada"

    # 4. Malayalam
    if (
        re.search(r"[\u0D00-\u0D7F]", raw)
        or re.search(
            r"\bmalayalam\b|മലയാളം|xylem\s*neet|xylem\s*plus|xylem\s*learning|\bxylem\b|"
            r"eduport|exam\s*winner|brilliant\s*pala|pw\s*malayalam|physics\s*wallah\s*malayalam|"
            r"vedantu\s*plus\s*one",
            blob,
        )
    ):
        return "Malayalam"

    # 5. Bengali
    if (
        re.search(r"[\u0980-\u09FF]", raw)
        or re.search(
            r"\bbangla\b|\bbengali\b|বাংলা|pw\s*bangla|physics\s*wallah\s*bangla|"
            r"bong\s*mistry|soe\s*bangla|biology\s*haters|science\s*beta|unacademy\s*bangla",
            blob,
        )
    ):
        return "Bengali"

    # 6. Marathi (checked before Devanagari Hindi so Marathi Devanagari titles -> 'Marathi')
    if re.search(
        r"\bmarathi\b|मराठी|physics\s*gyan|mukesh\s*nayak|sovind\s*sir|all\s*about\s*chemistry|"
        r"new\s*indian\s*era|dinesh\s*sir|shubham\s*muley|giri\s*tutorials|pradeep\s*giri|pawan\s*wagh|"
        r"pw\s*maharashtra|pw\s*mht\s*cet|physics\s*wallah\s*maharashtra",
        blob,
    ):
        return "Marathi"

    # 7. Gujarati
    if (
        re.search(r"[\u0A80-\u0AFF]", raw)
        or re.search(
            r"\bgujarati\b|ગુજરાતી|pw\s*gujarat\w*|gshseb|physics\s*wallah\s*gujarati|"
            r"vidyakul\s*gujarati|youth\s*vidyakul|youth\s*education|diwalipura|nimesh\s*sir",
            blob,
        )
    ):
        return "Gujarati"

    # 8. Odia
    if (
        re.search(r"[\u0B00-\u0B7F]", raw)
        or re.search(
            r"\bodia\b|\boriya\b|ଓଡ଼ିଆ|pw\s*odia|pw\s*odisha|physics\s*wallah\s*odia|"
            r"chse\s*catalyst|vidyant\s*chse|matsci\s*odia|matsci\s*science",
            blob,
        )
    ):
        return "Odia"

    # 9. Punjabi
    if (
        re.search(r"[\u0A00-\u0A7F]", raw)
        or re.search(
            r"\bpunjabi\b|ਪੰਜਾਬੀ|pw\s*punjabi|pw\s*punjab|punjab\s*board|physics\s*wallah\s*punjabi",
            blob,
        )
    ):
        return "Punjabi"

    # 10. Hindi (explicit Hindi-medium channels/cues or Devanagari script without Marathi cues)
    if (
        re.search(
            r"hindi\s*medium|हिंदी\s*माध्यम|pw\s*hindi|physics\s*wallah\s*hindi|neet\s*hindi|"
            r"ashish\s*singh\s*lectures|learn\s*and\s*share|science\s*sangrah|anu\s*sir\s*bihar\s*board|"
            r"doubtnut.*hindi|utkarsh",
            blob,
        )
        or re.search(r"[\u0900-\u097F]", raw)
    ):
        return "Hindi"

    # 11. English
    if re.search(
        r"\bin\s+(?:pure\s+)?english\b|\benglish\s+medium\b|\bpure\s+english\b|\bneet\s+english\b|"
        r"vedantu\s*neet\s*english|unacademy\s*neet\s*english|khan\s*academy\s*india\s*-\s*english|"
        r"\bpw\s+english\b|infinity\s*learn\s*neet",
        blob,
    ):
        if not re.search(r"\bhinglish\b|\bhindi\b", blob):
            return "English"

    # 12. Default pan-India Hindi+English
    return "Hinglish"


def classify_exam_and_format(cand: dict) -> tuple[str, str]:
    title_low = cand["title"].lower()
    ch_low = cand["channel"].lower()
    blob = f"{title_low} {ch_low}"

    if cand["provider"] == "playlist":
        fmt = "Full Course"
        if re.search(r"\b(ncert\s*line|ncert\s*highlight|ncert\s*nichod|ncert\s*decoding|ncert\s*reading)\b", title_low):
            fmt = "NCERT Line-by-Line"
        elif re.search(r"\b(pyq\w*|previous year|revision|formula|mind\s*map|short\s*notes|most\s*expected|top\s+\d+)\b", title_low):
            fmt = "Revision & PYQs"
    else:
        if re.search(r"\b(ncert\s*line|ncert\s*highlight|ncert\s*nichod|ncert\s*decoding|ncert\s*extract|line\s*by\s*line)\b", title_low):
            fmt = "NCERT Line-by-Line"
        elif (
            re.search(r"\b(pyq\w*|previous year|mind\s*map|formula|cheat\s*sheet|rapid\s*revision|short\s*notes|top\s+\d+|most\s*expected)\b", title_low)
            and "one shot" not in title_low
        ):
            fmt = "Revision & PYQs"
        else:
            fmt = "One-Shot"

    # Clean canonical target_exam classification (4 tiers)
    if re.search(
        r"\b(b\.?\s*sc\.?\s*nursing|nursing|paramedical|vijay\s*education|ruhs|abvmu|"
        r"kcet|mht[\s-]*cet|eamcet|eapcet|keam|gujcet|jenpas|ojee|bcece)\b",
        blob,
    ):
        exam = "Medical, Nursing & State CET"
    elif re.search(
        r"\b(aiims|jipmer|ncert\s*exemplar|exemplar|assertion|statement\s*based|rank\s*booster|"
        r"neet\s*toppers|air\s*1\b|ncert\s*nichod|ncert\s*extract|ncert\s*line\s*by\s*line)\b"
        r"|(?:360\s*/\s*360|180\s*/\s*180|700\s*\+|680\s*\+|650\s*\+)",
        blob,
    ):
        exam = "NEET + AIIMS"
    elif (
        re.search(
            r"\b(cbse|board\s*exam|boards?\s*202\d|class\s*12\s*board|12th\s*board|hsc|2nd\s*puc|1st\s*puc|"
            r"plus\s*two|plus\s*one|ipe\b|wbchse|chse|gseb|gshseb|punjab\s*board|pseb|up\s*board|bihar\s*board|rbse|vijeta)\b|बोर्ड",
            blob,
        )
        and not re.search(r"\bneet\b", title_low)
    ) or (
        any(
            b_ch in ch_low
            for b_ch in (
                "sourabh raina",
                "bharat panchal",
                "chemistry guruji",
                "arvind academy",
                "munil sir",
                "science and fun",
                "ashu ghai 11th",
                "next toppers",
                "class 12 by unacademy",
                "learnohub",
                "magnet brains",
                "science sangrah",
                "anu sir bihar board",
                "new indian era",
                "giri tutorials",
                "pradeep giri",
                "pawan wagh",
                "chse catalyst",
                "vidyant chse",
                "pw odisha",
                "pw punjab board",
                "vidyakul",
                "youth education",
                "diwalipura",
            )
        )
        and not re.search(r"\bneet\b", title_low)
    ):
        exam = "Class 12 & Boards"
    else:
        exam = "NEET UG"

    return exam, fmt


def is_valid_chapter_candidate(cand: dict, ch_no: int, subject: str, chapter_re: re.Pattern[str]) -> bool:
    title = cand["title"]
    channel = cand["channel"]

    # 1. Must belong to our Verified Educator / Official Institute Channel allowlist
    if not is_verified_neet_channel(channel):
        return False

    # 2. Reject JEE-Advanced-only, Class 6/7/8/9/10, SSC/Railway/UPSC, and non-lecture noise
    if HARD_REJECT_RE.search(title):
        return False
    # Reject JEE-only titles that do not mention NEET/AIIMS/Medical/Nursing/Boards/State-CET
    if re.search(r"\b(jee|iit|wbjee)\b", title, re.I) and not re.search(
        r"\b(neet|aiims|medical|nursing|cbse|boards?|hsc|puc|plus\s*(?:one|two)|chse|wbchse|gseb|kcet|mht[\s-]*cet|eamcet|eapcet|keam|gujcet|jenpas)\b",
        title,
        re.I,
    ):
        return False

    # 3. Chapter-level disambiguation guards
    # Ch 6 (Cell: Unit of Life) vs Ch 7 (Cell Cycle & Cell Division)
    if (
        ch_no == 6
        and re.search(r"\b(cell cycle|cell division|mitosis|meiosis)\b|कोशिका\s*चक्र|कोशिका\s*विभाजन|समसूत्री|अर्धसूत्री", title, re.I)
        and not re.search(r"\bunit of life\b|जीवन\s*की\s*इकाई", title, re.I)
    ):
        return False
    # Ch 12 (Principles of Inheritance) vs Ch 13 (Molecular Basis of Inheritance)
    if (
        ch_no == 12
        and re.search(r"\bmolecular basis\b|आणविक\s*आधार", title, re.I)
        and not re.search(r"\bprinciples? of inheritance\b|वंशागति\s*के\s*सिद्धांत", title, re.I)
    ):
        return False
    if (
        ch_no == 13
        and re.search(r"\bprinciples? of inheritance\b|वंशागति\s*(?:तथा|और)\s*विविधता", title, re.I)
        and not re.search(r"\bmolecular\b|आणविक", title, re.I)
    ):
        return False
    # Ch 20 (Zoology Biomolecules) vs Ch 72 (Chemistry Biomolecules & Practical Chemistry)
    if ch_no == 20 and re.search(
        r"\b(chemistry|organic|class\s*12|12th|plus\s*two|2nd\s*puc|hsc|practical|salt analysis|\bpoc\b|"
        r"pankaj\s*sir|vt\s*sir|nitesh\s*devnani|yogesh\s*jain|amit\s*mahajan|sudhanshu|wassim|"
        r"mohit\s*dadheech|hitesh\s*sopra|akansha\s*karnwal|bharat\s*panchal|chemistry\s*guruji|"
        r"bong\s*mistry|sovind\s*sir|all\s*about\s*chemistry|nimesh\s*sir)\b|रसायन|कक्षा\s*12",
        f"{title} {channel}",
        re.I,
    ):
        return False
    if ch_no == 72:
        if re.search(
            r"\b(biology|zoology|botany|class\s*11\s*bio\w*|plus\s*one\s*bio\w*|seep\s*pahuja|garima\s*goel|"
            r"ritu\s*rattewal|vipin\s*sharma|ozone\s*classes|kv\s*education|tarun\s*sir|samapti|manish\s*dubey|"
            r"md\s*sir|rupesh|akanksha\s*agarwal|vani\s*ma'?am|biotonic|gargi|biology\s*simplified|biology\s*haters)\b|जीव\s*विज्ञान",
            f"{title} {channel}",
            re.I,
        ):
            return False
        if re.search(r"\bbiomolecules?\b|जैव[\s-]*अणु", title, re.I) and not re.search(
            r"\b(chemistry|organic|class\s*12|12th|plus\s*two|2nd\s*puc|hsc|practical|salt\s*analysis|\bpoc\b|"
            r"carbohydrates?|glucose|pankaj|vt\s*sir|nitesh|yogesh|amit\s*mahajan|sudhanshu|wassim|"
            r"akansha\s*karnwal|bharat\s*panchal|chemistry\s*guruji|bong\s*mistry|sovind\s*sir|"
            r"all\s*about\s*chemistry|nimesh\s*sir|sourabh\s*raina)\b|रसायन|कार्बोहाइड्रेट",
            f"{title} {channel}",
            re.I,
        ):
            return False
    # Ch 27 (Human Reproduction) vs Ch 28 (Reproductive Health)
    if (
        ch_no == 27
        and re.search(r"\breproductive health\b|जनन\s*स्वास्थ्य", title, re.I)
        and not re.search(r"\bhuman reproduction\b|मानव\s*जनन", title, re.I)
    ):
        return False
    # Ch 31 (Biotech Principles) vs Ch 32 (Biotech Applications)
    if ch_no == 31 and re.search(r"\bapplications?\b|उपयोग|अनुप्रयोग", title, re.I) and not re.search(r"\bprinciples?\b|सिद्धांत", title, re.I):
        return False
    if ch_no == 32 and re.search(r"\bprinciples?\s*(?:and|&)\s*processes\b|सिद्धांत\s*एवं\s*प्रक्रम", title, re.I) and not re.search(r"\bapplications?\b|उपयोग|अनुप्रयोग", title, re.I):
        return False
    # Ch 34 (1D Motion) vs Ch 35 (2D Motion & Projectile)
    if ch_no == 34 and re.search(r"\b(motion in a plane|projectile|2\s*-?\s*d)\b|समतल\s*में\s*गति|प्रक्षेप्य", title, re.I) and not re.search(r"\bstraight line\b|सरल\s*रेखा", title, re.I):
        return False
    if ch_no == 35 and re.search(r"\bmotion in a straight line\b|सरल\s*रेखा\s*में\s*गति", title, re.I) and not re.search(r"\b(plane|projectile)\b|समतल|प्रक्षेप्य", title, re.I):
        return False
    # Ch 44 (Waves & Sound) vs EM Waves / Matter Waves / Wave Optics
    if ch_no == 44 and re.search(r"\b(electromagnetic waves?|\bem\s+waves?\b|matter waves?|wave optics)\b|तरंग\s*प्रकाशिकी|विद्युत\s*चुंबकीय\s*तरंग", title, re.I):
        return False
    # Ch 45 (Electric Charges, Fields & Potential) vs Ch 46 (Capacitors & Current Electricity)
    if ch_no == 45 and re.search(r"\b(capacitors?|capacitance|current electricity)\b|विद्युत\s*धारा|वैद्युत\s*धारा|संधारित्र", title, re.I) and not re.search(r"\b(charges?|fields?|potential|electrostatics?|gauss)\b|वैद्युत\s*आवेश|विद्युत\s*आवेश|स्थिर\s*वैद्युतिकी|विभव", title, re.I):
        return False
    # Ch 47 (Moving Charges) vs Ch 48 (Magnetism, Matter & EMI)
    if ch_no == 47 and re.search(r"\b(magnetism\s*(?:and|&)\s*matter|electromagnetic induction|\bemi\b)\b|विद्युत\s*चुंबकीय\s*प्रेरण|चुंबकत्व\s*एवं\s*द्रव्य", title, re.I) and not re.search(r"\bmoving charges\b|गतिमान\s*आवेश", title, re.I):
        return False
    # Ch 50 (Ray Optics) vs Ch 51 (Wave Optics)
    if ch_no == 50 and re.search(r"\bwave optics\b|तरंग\s*प्रकाशिकी", title, re.I) and not re.search(r"\b(ray optics|geometrical optics)\b|किरण\s*प्रकाशिकी", title, re.I):
        return False
    # Ch 52 (Modern Physics) vs Ch 54 (Chemistry Structure of Atom)
    if ch_no == 52 and re.search(r"\b(structure of atom|atomic structure)\b|परमाणु\s*की\s*संरचना", title, re.I) and not re.search(r"\b(modern physics|nuclei|semiconductor|dual nature|physics)\b|भौतिकी|नाभिक|अर्धचालक", title, re.I):
        return False
    # Ch 60 (Solutions & Colligative Properties) — prevent generic "Paper/NCERT Solutions" match
    if ch_no == 60 and not re.search(
        r"\b(liquid|dilute|colligative|raoult|van'?t\s*hoff|henry|one[\s-]*shot|1[\s-]*shot|full\s+chapter|"
        r"class\s*12|12th|plus\s*two|2nd\s*puc|hsc|chse|wbchse|chemistry|prachand|umeed|aarambh|yakeen)\b"
        r"|विलयन|अणुसंख्य|राउल्ट|रसायन",
        title,
        re.I,
    ):
        return False
    # Ch 66 (IUPAC & Isomerism) vs Ch 64 (Coordination Compounds isomerism)
    if ch_no == 66 and re.search(r"\bcoordination\b|उपसहसंयोजन", title, re.I):
        return False
    # Ch 67 (Hydrocarbons) vs Ch 68 (Haloalkanes & Haloarenes)
    if ch_no == 67 and re.search(r"\b(haloalkanes?|haloarenes?|halogen derivatives?)\b|हैलोएल्केन|हैलोएरीन", title, re.I) and not re.search(r"\bhydrocarbons?\b|हाइड्रोकार्बन", title, re.I):
        return False

    # 4. Reject full-subject megacompilations ("complete biology in one video", "all chapters")
    if re.search(
        r"\b(all\s+chapters|complete\s+(?:class\s*1[12]\s+|plus\s*two\s+|2nd\s*puc\s+)?(?:biology|botany|zoology|physics|chemistry|organic|inorganic|physical)\s+in\s+one)\b",
        title,
        re.I,
    ):
        return False
    if cand["provider"] == "playlist" and re.search(r"\bin order\b|\ball chapters\b|\bcomplete (?:biology|botany|zoology|physics|chemistry)\b", title, re.I):
        if not chapter_re.search(title):
            return False

    # 5. Avoid isolated mid-series short lecture fragments ("Part 7", "Lec 14") for single videos < 60m
    if cand["provider"] == "youtube" and 0 < cand["duration_sec"] < 3600:
        if re.search(r"(?:^|\b)(?:part|lec(?:ture)?|ep(?:isode)?|l)\s*[-#.]?\s*(?:[2-9]|\d{2,})\b|^#\d+\b", title, re.I):
            if not re.search(r"\b(pyq|revision|ncert|mind\s*map|one\s*shot)\b", title, re.I):
                return False

    # 6. Strict Chapter-Title Keyword Match
    if not chapter_re.search(title):
        return False

    # 7. Cross-Subject Guards (check hashtag-stripped title & specialist teacher cues; never penalize "Physics Wallah" channel on Bio/Chem)
    title_clean = re.sub(r"#\w+", "", title)
    blob_tc = f"{title_clean} {channel}"

    if subject in ("Botany", "Zoology"):
        if re.search(
            r"\b(mr\s*sir|tamanna\s*chaudhary|prateek\s*jain|mahendra\s*singh|ayudh|arvind\s*academy|munil\s*sir|"
            r"physics\s*gyan|mukesh\s*nayak|simplified\s*minds|educare\s*karnataka|matsci\s*odia|science\s*beta|"
            r"pankaj\s*sir|vt\s*sir|vishal\s*tiwari|nitesh\s*devnani|amit\s*mahajan|sudhanshu|yogesh\s*jain|"
            r"wassim\s*bhat|bharat\s*panchal|chemistry\s*guruji|bong\s*mistry|sovind\s*sir|all\s*about\s*chemistry|"
            r"nimesh\s*sir|kinematics|electrostatics|mole\s*concept|organic\s*chemistry|inorganic\s*chemistry|physical\s*chemistry)\b",
            blob_tc,
            re.I,
        ) or re.search(
            r"\b(neet\s+physics|neet\s+chemistry|class\s*1[12]\s*(?:physics|chemistry)|plus\s*(?:one|two)\s*(?:physics|chemistry)|"
            r"2nd\s*puc\s*(?:physics|chemistry)|mathematics|maths)\b|भौतिक\s*विज्ञान|रसायन\s*विज्ञान|गणित",
            title_clean,
            re.I,
        ):
            return False
    elif subject == "Physics":
        if re.search(
            r"\b(seep\s*pahuja|garima\s*goel|ritu\s*rattewal|vipin\s*sharma|ozone\s*classes|kv\s*education|tarun\s*sir|"
            r"samapti|biology\s*simplified|senthilnathan|biology\s*haters|sourabh\s*raina|"
            r"pankaj\s*sir|vt\s*sir|vishal\s*tiwari|nitesh\s*devnani|amit\s*mahajan|sudhanshu|yogesh\s*jain|"
            r"wassim\s*bhat|bharat\s*panchal|chemistry\s*guruji|bong\s*mistry|sovind\s*sir|all\s*about\s*chemistry|"
            r"nimesh\s*sir|mole\s*concept|enthalpy|gibbs|chemical\s*thermodynamics|thermochemistry|chemical\s*kinetics|botany|zoology)\b",
            blob_tc,
            re.I,
        ) or re.search(r"\b(chemistry|biology|botany|zoology|mathematics|maths)\b|रसायन\s*विज्ञान|जीव\s*विज्ञान|गणित", title_clean, re.I):
            return False
    elif subject == "Chemistry":
        if re.search(
            r"\b(seep\s*pahuja|garima\s*goel|ritu\s*rattewal|vipin\s*sharma|ozone\s*classes|kv\s*education|tarun\s*sir|"
            r"samapti|biology\s*simplified|senthilnathan|biology\s*haters|"
            r"mr\s*sir|tamanna\s*chaudhary|prateek\s*jain|mahendra\s*singh|ayudh|arvind\s*academy|munil\s*sir|"
            r"physics\s*gyan|mukesh\s*nayak|educare\s*karnataka|matsci\s*odia|"
            r"kinematics|rotational|carnot|\bktg\b|kinetic\s*theory\s*of\s*gases|modern\s*physics|semiconductors?|botany|zoology)\b",
            blob_tc,
            re.I,
        ) or re.search(
            r"\b(neet\s+physics|class\s*1[12]\s*physics|plus\s*(?:one|two)\s*physics|2nd\s*puc\s*physics|biology|botany|zoology|mathematics|maths)\b|भौतिक\s*विज्ञान|जीव\s*विज्ञान|गणित",
            title_clean,
            re.I,
        ):
            return False

    # 8. Duration & Lesson Count Floor
    if cand["provider"] == "playlist":
        if cand["lesson_count"] == 1:
            return False
    else:
        if 0 < cand["duration_sec"] < 900:
            return False

    return True


def parse_age_months(published_text: str) -> float:
    """Parse YouTube relative published text ('3 weeks ago', 'Streamed 4 months ago') into months."""
    if not published_text:
        return 18.0
    low = published_text.lower()
    m = re.search(r"(\d+)\s*(hour|day|week|month|year)", low)
    if not m:
        return 18.0
    n = float(m.group(1))
    unit = m.group(2)
    if unit == "hour":
        return 0.15
    if unit == "day":
        return max(0.2, n / 30.0)
    if unit == "week":
        return max(0.3, (n * 7.0) / 30.0)
    if unit == "month":
        return max(0.5, n)
    if unit == "year":
        return max(12.0, n * 12.0)
    return 18.0


def compute_trend_metrics(cand: dict, fmt: str) -> tuple[float, int, float, str]:
    """Compute pure YouTube audience trend score with ZERO coaching/institute priority.

    Returns (age_months, views_per_month, trend_score, trend_badge).
    """
    if cand["provider"] == "playlist":
        lessons = cand["lesson_count"]
        t_score = 64.0 + min(lessons, 45) * 0.42 + (3.5 if cand.get("sample_lectures") else 0.0)
        badge = f"📚 {lessons} Lectures" if lessons else "📚 Full Playlist"
        return 12.0, 0, round(t_score, 2), badge

    views = max(int(cand.get("view_count") or 0), 1)
    age_m = parse_age_months(cand.get("published") or "")
    vpm = int(round(views / max(age_m, 0.75)))

    # Pure YouTube traction formula: monthly view velocity + total student reach + freshness
    velocity_pts = math.log10(max(vpm, 1)) * 13.5
    reach_pts = math.log10(views) * 9.5
    freshness_pts = 8.0 if age_m <= 6.0 else (4.5 if age_m <= 14.0 else (2.0 if age_m <= 24.0 else 0.0))
    depth_pts = 3.5 if cand.get("duration_sec", 0) >= 5400 else 1.5
    t_score = round(velocity_pts + reach_pts + freshness_pts + depth_pts, 2)

    if vpm >= 35_000 or (age_m <= 8.0 and views >= 120_000):
        badge = "🔥 Trending"
    elif views >= 1_000_000:
        badge = "⭐ Most Loved"
    elif views >= 250_000 or vpm >= 12_000:
        badge = "📈 Popular"
    else:
        badge = f"⚡ {fmt}"

    return round(age_m, 1), vpm, t_score, badge


def build_pedagogy_note(cand: dict, educator: str, exam: str, fmt: str, chapter_name: str) -> str:
    if cand["provider"] == "playlist":
        lessons = f"{cand['lesson_count']}-lecture " if cand["lesson_count"] else "Complete "
        return f"{lessons}YouTube playlist by {educator} · {exam} ({chapter_name})."
    parts = []
    if cand["duration"]:
        parts.append(f"{cand['duration']} {fmt.lower()}")
    else:
        parts.append(fmt)
    parts.append(f"by {educator}")
    if cand["views_text"]:
        parts.append(f"· {cand['views_text']}")
    return " ".join(parts)


def build_corpus(use_cache: bool = True) -> dict:
    compiled_chapters = []
    chapter_tasks = []
    for row in SYLLABUS:
        ch_no, subject, unit, class_lvl, weightage, scope, ch_name, pat, core_q, alt_q = row
        cre = re.compile(pat, re.I)
        compiled_chapters.append((ch_no, subject, unit, class_lvl, weightage, scope, ch_name, cre))
        # Pure organic YouTube NEET queries (zero institute stuffing; hits cache instantaneously)
        chapter_tasks.append(("chapter", ch_no, subject, cre, f"{core_q} NEET", SP_PLAYLIST_ONLY))
        chapter_tasks.append(("chapter", ch_no, subject, cre, f"{alt_q} NEET", SP_PLAYLIST_ONLY))
        chapter_tasks.append(("chapter", ch_no, subject, cre, f"{core_q} NEET one shot", SP_LONG_VIDEOS))
        chapter_tasks.append(("chapter", ch_no, subject, cre, f"{alt_q} NEET one shot NCERT", SP_LONG_VIDEOS))
        chapter_tasks.append(("chapter", ch_no, subject, cre, f"{core_q} NEET PYQ revision", SP_LONG_VIDEOS))

    for subj, tq in TEACHER_PLAYLIST_SWEEPS:
        chapter_tasks.append(("sweep", 0, subj, None, tq, SP_PLAYLIST_ONLY))
    for subj, vq in INSTITUTE_VIDEO_SWEEPS:
        chapter_tasks.append(("sweep", 0, subj, None, vq, SP_LONG_VIDEOS))

    print(
        f"Executing {len(chapter_tasks)} YouTube InnerTube queries across {len(SYLLABUS)} NEET UG & PCB chapters...",
        flush=True,
    )

    raw_results: dict[int, list[dict]] = {row[0]: [] for row in SYLLABUS}
    sweep_candidates: list[tuple[str, dict]] = []

    def worker(task):
        kind, ch_no, subject, cre, query, sp = task
        payload = search_youtube(query, params=sp, use_cache=use_cache)
        cands = extract_candidates(payload)
        if kind == "chapter":
            kept = [c for c in cands if is_valid_chapter_candidate(c, ch_no, subject, cre)]
            return kind, ch_no, subject, kept
        return kind, 0, subject, cands

    with ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(worker, t) for t in chapter_tasks]
        for fut in as_completed(futures):
            kind, ch_no, subject, items = fut.result()
            if kind == "chapter":
                raw_results[ch_no].extend(items)
            else:
                for c in items:
                    sweep_candidates.append((subject, c))

    # Specialized chapters claim ambiguous items first
    specialized_first = {7, 13, 20, 28, 31, 32, 35, 46, 48, 51, 54, 64, 66, 68, 72}
    priority_chapters = sorted(
        compiled_chapters,
        key=lambda c: (0 if c[0] in specialized_first else 1, c[0]),
    )
    for subj, cand in sweep_candidates:
        allowed_subjects = ("Botany", "Zoology") if subj == "Biology" else (subj,)
        for ch_no, c_subj, _, _, _, _, _, cre in priority_chapters:
            if c_subj in allowed_subjects and is_valid_chapter_candidate(cand, ch_no, c_subj, cre):
                raw_results[ch_no].append(cand)
                break

    processing_order = sorted(
        compiled_chapters,
        key=lambda c: (0 if c[0] in specialized_first else 1, c[0]),
    )

    seen_global: set[tuple[str, str]] = set()
    chapter_records_map: dict[int, list[dict]] = {}
    chapter_meta_map: dict[int, dict] = {}

    rep_languages = (
        "Tamil",
        "Malayalam",
        "Telugu",
        "Kannada",
        "Bengali",
        "Marathi",
        "Gujarati",
        "Odia",
        "Punjabi",
        "Hindi",
        "English",
    )
    rep_streams = (
        "Medical, Nursing & State CET",
        "Class 12 & Boards",
        "NEET + AIIMS",
    )
    max_chapter_items = 36

    for ch_no, subject, unit, class_lvl, weightage, scope, ch_name, _ in processing_order:
        candidates = raw_results[ch_no]

        enriched = []
        seen_local: set[tuple[str, str]] = set()
        for cand in candidates:
            gkey = (cand["provider"], cand["video_id"])
            if gkey in seen_global or gkey in seen_local:
                continue
            seen_local.add(gkey)
            exam, fmt = classify_exam_and_format(cand)
            lang = resolve_language(cand)
            age_m, vpm, t_score, t_badge = compute_trend_metrics(cand, fmt)
            enriched.append((t_score, age_m, vpm, t_badge, exam, fmt, lang, cand))

        # Pure YouTube Trend & Popularity pools — ZERO artificial institute priority
        videos_pool = sorted(
            [x for x in enriched if x[7]["provider"] == "youtube"],
            key=lambda x: (-x[0], -x[2], -x[7]["view_count"], -x[7]["lesson_count"]),
        )
        playlists_pool = sorted(
            [x for x in enriched if x[7]["provider"] == "playlist"],
            key=lambda x: (-x[0], -x[2], -x[7]["view_count"], -x[7]["lesson_count"]),
        )

        unique_ch: list[dict] = []
        edu_cap: dict[str, int] = {}

        def _append_item(entry_tuple: tuple, per_edu_max: int) -> bool:
            t_score, age_m, vpm, t_badge, exam, fmt, lang, cand = entry_tuple
            gkey = (cand["provider"], cand["video_id"])
            if gkey in seen_global:
                return False
            institute = resolve_institute(cand)
            educator = resolve_educator(cand, subject, unit)
            ekey = f"{educator.casefold()}::{cand['provider']}"
            if edu_cap.get(ekey, 0) >= per_edu_max:
                return False
            seen_global.add(gkey)
            edu_cap[ekey] = edu_cap.get(ekey, 0) + 1

            unique_ch.append(
                {
                    "provider": cand["provider"],
                    "video_id": cand["video_id"],
                    "embed_video_id": cand["embed_video_id"],
                    "url": cand["url"],
                    "title": cand["title"],
                    "channel": cand["channel"],
                    "channel_url": cand["channel_url"],
                    "institute": institute,
                    "educator": educator,
                    "language": lang,
                    "thumbnail": cand["thumbnail"],
                    "subject": subject,
                    "unit": unit,
                    "chapter_no": ch_no,
                    "chapter": ch_name,
                    "class_level": class_lvl,
                    "weightage": weightage,
                    "syllabus_scope": scope,
                    "target_exam": exam,
                    "format": fmt,
                    "lesson_count": cand["lesson_count"],
                    "duration": cand["duration"],
                    "duration_sec": cand["duration_sec"],
                    "views_text": cand["views_text"],
                    "view_count": cand["view_count"],
                    "published": cand["published"],
                    "age_months": age_m,
                    "views_per_month": vpm,
                    "trend_score": t_score,
                    "trend_badge": t_badge,
                    "score": t_score,
                    "note": build_pedagogy_note(cand, educator, exam, fmt, ch_name),
                    "sample_lectures": cand.get("sample_lectures") or [],
                }
            )
            return True

        def _try_take(pool_items: list, limit_count: int, per_edu_max: int) -> None:
            for item in pool_items:
                if len(unique_ch) >= limit_count:
                    break
                _append_item(item, per_edu_max)

        # 1. Base selection purely by YouTube Trend & Popularity (14 top trending videos + 8 top playlists)
        _try_take(videos_pool, 14, 2)
        _try_take(playlists_pool, len(unique_ch) + 8, 2)
        combined_pool = sorted(
            videos_pool + playlists_pool,
            key=lambda x: (-x[0], -x[2], -x[7]["view_count"], -x[7]["lesson_count"]),
        )
        if len(unique_ch) < 20:
            _try_take(combined_pool, 22, 3)

        # 2. Multi-Language & Stream Representation Pass (up to 1-2 slots each, max 36 per chapter)
        # Round 1 guarantees every available underrepresented language & stream gets at least 1 slot first;
        # Round 2 adds a 2nd slot where room remains.
        for target_slots in (1, 2):
            for lang_name in rep_languages:
                if len(unique_ch) >= max_chapter_items:
                    break
                cur_cnt = sum(1 for r in unique_ch if r["language"] == lang_name)
                if cur_cnt >= target_slots:
                    continue
                for item in combined_pool:
                    if item[6] == lang_name and _append_item(item, 2):
                        break

            for stream_name in rep_streams:
                if len(unique_ch) >= max_chapter_items:
                    break
                cur_cnt = sum(1 for r in unique_ch if r["target_exam"] == stream_name)
                if cur_cnt >= target_slots:
                    continue
                for item in combined_pool:
                    if item[4] == stream_name and _append_item(item, 2):
                        break

        # 3. CRITICAL: Sort strictly by -trend_score, -views_per_month, -view_count, -lesson_count (ZERO institute priority)
        unique_ch.sort(
            key=lambda r: (
                -r["trend_score"],
                -r["views_per_month"],
                -r["view_count"],
                -r["lesson_count"],
            )
        )

        # Assert monotonic trend_score order & canonical strings
        for i in range(len(unique_ch) - 1):
            assert unique_ch[i]["trend_score"] >= unique_ch[i + 1]["trend_score"], (
                f"Non-monotonic trend_score in Ch {ch_no}: {unique_ch[i]['trend_score']} < {unique_ch[i + 1]['trend_score']}"
            )
        for r in unique_ch:
            assert r["language"] in CANONICAL_LANGUAGES, f"Invalid language: {r['language']}"
            assert r["target_exam"] in CANONICAL_EXAMS, f"Invalid target_exam: {r['target_exam']}"

        pl_cnt = sum(1 for r in unique_ch if r["provider"] == "playlist")

        yt_pl_q = urllib.parse.quote_plus(f"{ch_name} NEET")
        yt_os_q = urllib.parse.quote_plus(f"{ch_name} NEET one shot")

        chapter_records_map[ch_no] = unique_ch
        chapter_meta_map[ch_no] = {
            "chapter_no": ch_no,
            "subject": subject,
            "unit": unit,
            "class_level": class_lvl,
            "weightage": weightage,
            "syllabus_scope": scope,
            "chapter": ch_name,
            "count": len(unique_ch),
            "playlist_count": pl_cnt,
            "video_count": len(unique_ch) - pl_cnt,
            "yt_playlists_url": f"https://www.youtube.com/results?search_query={yt_pl_q}&sp=EgIQAw%253D%253D",
            "yt_oneshots_url": f"https://www.youtube.com/results?search_query={yt_os_q}&sp=EgIYAg%253D%253D",
        }

    # Assemble in canonical syllabus order 1..72
    syllabus_out = [chapter_meta_map[n] for n in range(1, len(SYLLABUS) + 1)]
    all_entries: list[dict] = []
    for n in range(1, len(SYLLABUS) + 1):
        ch_list = chapter_records_map[n]
        for i in range(len(ch_list) - 1):
            assert (
                ch_list[i]["trend_score"],
                ch_list[i]["views_per_month"],
                ch_list[i]["view_count"],
                ch_list[i]["lesson_count"],
            ) >= (
                ch_list[i + 1]["trend_score"],
                ch_list[i + 1]["views_per_month"],
                ch_list[i + 1]["view_count"],
                ch_list[i + 1]["lesson_count"],
            ), f"Strict trend ordering violated in Chapter {n}"
        all_entries.extend(ch_list)

    by_score = sorted(
        all_entries,
        key=lambda x: (
            -x["trend_score"],
            -x["views_per_month"],
            -x["view_count"],
            -x["lesson_count"],
            x["chapter_no"],
        ),
    )
    for idx, rec in enumerate(by_score, 1):
        rec["global_rank"] = idx

    edu_buckets: dict[str, dict] = {}
    for rec in all_entries:
        edu = rec["educator"]
        if edu not in edu_buckets:
            edu_buckets[edu] = {
                "educator": edu,
                "subjects": Counter(),
                "total": 0,
                "playlists": 0,
                "videos": 0,
                "chapters": set(),
            }
        b = edu_buckets[edu]
        b["subjects"][rec["subject"]] += 1
        b["total"] += 1
        b["chapters"].add(rec["chapter_no"])
        if rec["provider"] == "playlist":
            b["playlists"] += 1
        else:
            b["videos"] += 1

    educators_out = []
    for edu, b in edu_buckets.items():
        primary_subject = b["subjects"].most_common(1)[0][0]
        educators_out.append(
            {
                "educator": edu,
                "subject": primary_subject,
                "total": b["total"],
                "playlists": b["playlists"],
                "videos": b["videos"],
                "chapter_coverage": len(b["chapters"]),
            }
        )
    educators_out.sort(
        key=lambda e: (
            -e["total"],
            -e["playlists"],
            e["educator"],
        )
    )

    inst_buckets: dict[str, dict] = {}
    for rec in all_entries:
        inst = rec["institute"]
        if inst not in inst_buckets:
            inst_buckets[inst] = {
                "institute": inst,
                "total": 0,
                "playlists": 0,
                "videos": 0,
                "chapters": set(),
            }
        ib = inst_buckets[inst]
        ib["total"] += 1
        ib["chapters"].add(rec["chapter_no"])
        if rec["provider"] == "playlist":
            ib["playlists"] += 1
        else:
            ib["videos"] += 1

    institutes_out = [
        {
            "institute": inst,
            "total": ib["total"],
            "playlists": ib["playlists"],
            "videos": ib["videos"],
            "chapter_coverage": len(ib["chapters"]),
        }
        for inst, ib in inst_buckets.items()
    ]
    institutes_out.sort(
        key=lambda i: (
            -i["total"],
            i["institute"],
        )
    )

    playlists_total = sum(1 for x in all_entries if x["provider"] == "playlist")
    chapters_with_pl = sum(1 for c in syllabus_out if c["playlist_count"] > 0)
    lang_counts = Counter(x["language"] for x in all_entries)
    exam_counts = Counter(x["target_exam"] for x in all_entries)

    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "chapters_total": len(SYLLABUS),
            "chapters_populated": sum(1 for c in syllabus_out if c["count"] > 0),
            "chapters_with_playlists": chapters_with_pl,
            "entries_published": len(all_entries),
            "playlists_published": playlists_total,
            "videos_published": len(all_entries) - playlists_total,
            "distinct_institutes": len(institutes_out),
            "distinct_educators": len(educators_out),
            "distinct_channels": len({x["channel"].casefold() for x in all_entries}),
            "distinct_languages": len(lang_counts),
            "languages": dict(lang_counts.most_common()),
            "target_exams": dict(exam_counts.most_common()),
            "queries_executed": len(chapter_tasks),
            "live_requests": STATS["requests"],
            "cached_requests": STATS["cached"],
        },
        "institutes": institutes_out,
        "educators": educators_out,
        "syllabus": syllabus_out,
        "videos": all_entries,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def self_test() -> None:
    assert len(SYLLABUS) == 72, f"Expected 72 canonical NEET UG chapters, got {len(SYLLABUS)}"
    nums = [r[0] for r in SYLLABUS]
    assert nums == list(range(1, 73)), "Chapter numbers must be contiguous 1..72"

    bot_chs = [r for r in SYLLABUS if r[1] == "Botany"]
    zoo_chs = [r for r in SYLLABUS if r[1] == "Zoology"]
    phy_chs = [r for r in SYLLABUS if r[1] == "Physics"]
    che_chs = [r for r in SYLLABUS if r[1] == "Chemistry"]
    assert (len(bot_chs), len(zoo_chs), len(phy_chs), len(che_chs)) == (17, 15, 20, 20), (
        f"Unexpected subject split: {(len(bot_chs), len(zoo_chs), len(phy_chs), len(che_chs))}"
    )

    assert parse_views("1.8M views") == 1_800_000
    assert parse_views("425K views") == 425_000
    assert parse_duration_seconds("7:42:15") == 27735
    assert parse_duration_seconds("45:10") == 2710

    cre_mol = re.compile(SYLLABUS[12][7], re.I)  # Ch 13 Molecular Basis of Inheritance
    good_vid = {
        "provider": "youtube",
        "video_id": "abcdefghijk",
        "title": "Molecular Basis of Inheritance in ONE SHOT | Complete NCERT | NEET 2025 | Vipin Sharma",
        "channel": "Competition Wallah",
        "lesson_count": 0,
        "duration_sec": 21600,
        "view_count": 2_400_000,
        "published": "5 months ago",
        "sample_lectures": [],
    }
    assert is_valid_chapter_candidate(good_vid, 13, "Botany", cre_mol)
    assert resolve_educator(good_vid, "Botany", "Genetics") == "Vipin Sharma (Ozone Classes)"
    assert resolve_institute(good_vid) == "Physics Wallah (PW)"
    assert resolve_language(good_vid) == "Hinglish"

    # Reject JEE Advanced / Irodov / MathonGo
    bad_jee_adv = {
        "provider": "youtube",
        "video_id": "12345678901",
        "title": "Rotational Motion Irodov & Pathfinder Solutions | JEE Advanced",
        "channel": "Physics Wallah",
        "lesson_count": 0,
        "duration_sec": 7200,
        "view_count": 150000,
        "sample_lectures": [],
    }
    cre_rot = re.compile(SYLLABUS[37][7], re.I)
    assert not is_valid_chapter_candidate(bad_jee_adv, 38, "Physics", cre_rot)

    # Validate All-India Regional & Hindi Medium support
    tamil_vid = {
        "provider": "youtube",
        "video_id": "tamil123456",
        "title": "Cell: The Unit of Life One Shot | NEET 2025 | Tamil",
        "channel": "Biology Simplified Tamil",
        "lesson_count": 0,
        "duration_sec": 5400,
        "view_count": 180000,
        "sample_lectures": [],
    }
    cre_cell = re.compile(SYLLABUS[5][7], re.I)
    assert is_valid_chapter_candidate(tamil_vid, 6, "Botany", cre_cell)
    assert resolve_language(tamil_vid) == "Tamil"

    hindi_vid = {
        "provider": "youtube",
        "video_id": "hindi123456",
        "title": "विलयन (Solutions) One Shot | रसायन विज्ञान Class 12 | NEET Hindi Medium",
        "channel": "PW Hindi Medium",
        "lesson_count": 0,
        "duration_sec": 7200,
        "view_count": 210000,
        "sample_lectures": [],
    }
    cre_sol = re.compile(SYLLABUS[59][7], re.I)
    assert is_valid_chapter_candidate(hindi_vid, 60, "Chemistry", cre_sol)
    assert resolve_language(hindi_vid) == "Hindi"

    assert resolve_language({"title": "Plus Two Biology", "channel": "Xylem NEET"}) == "Malayalam"
    assert resolve_language({"title": "NEET Biology", "channel": "Xylem NEET Tamil"}) == "Tamil"
    assert resolve_language({"title": "EAPCET Physics", "channel": "Vedantu Telugu"}) == "Telugu"
    assert resolve_language({"title": "KCET Physics", "channel": "SimplifiedMinds Karnataka"}) == "Kannada"
    assert resolve_language({"title": "Organic One Shot", "channel": "BongMistry"}) == "Bengali"
    assert resolve_language({"title": "Rotational Dynamics मराठी", "channel": "Physics Gyan - Mukesh Nayak"}) == "Marathi"
    assert resolve_language({"title": "GUJCET Chemistry", "channel": "Chemistry By NIMESHSIR"}) == "Gujarati"
    assert resolve_language({"title": "CHSE Biology", "channel": "PW Odia"}) == "Odia"
    assert resolve_language({"title": "Biology in English", "channel": "Vedantu NEET English"}) == "English"

    assert not is_verified_neet_channel("ALLEN JEE")
    assert not is_verified_neet_channel("MR Sir Fan Club")
    assert is_verified_neet_channel("Biology Simplified Tamil")
    assert is_verified_neet_channel("Vedantu Telugu")
    assert is_verified_neet_channel("Xylem NEET")
    assert is_verified_neet_channel("BongMistry")
    assert is_verified_neet_channel("Bharat Panchal - Chemistry Guruji 2.0")
    assert is_verified_neet_channel("Competition Wallah")

    print("self-test ok (72 canonical NCERT NEET UG chapters, 12 languages & pure-trend guards validated)", flush=True)


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        self_test()
        return 0
    self_test()
    use_cache = "--fresh" not in argv
    out = build_corpus(use_cache=use_cache)
    m = out["meta"]
    inst_lines = "\n".join(
        f"  - {i['institute']:<32}: {i['total']:>4} ({i['playlists']:>3} PL, {i['videos']:>3} vids across {i['chapter_coverage']:>2} ch)"
        for i in out["institutes"]
    )
    subj_counts = Counter(v["subject"] for v in out["videos"])
    subj_lines = "\n".join(f"  - {s:<12}: {subj_counts[s]:>4}" for s in ("Botany", "Zoology", "Physics", "Chemistry"))
    lang_counts = Counter(v["language"] for v in out["videos"])
    lang_lines = "\n".join(f"  - {lg:<12}: {cnt:>4}" for lg, cnt in lang_counts.most_common())
    exam_counts = Counter(v["target_exam"] for v in out["videos"])
    exam_lines = "\n".join(f"  - {ex:<30}: {cnt:>4}" for ex, cnt in exam_counts.most_common())
    low_chs = [c for c in out["syllabus"] if c["count"] < 6]
    print(
        f"\n=== NEETTUBE 72-CHAPTER ALL-INDIA CORPUS REPORT ===\n"
        f"Chapters populated      : {m['chapters_populated']} / {m['chapters_total']}\n"
        f"Chapters with playlists : {m['chapters_with_playlists']} / {m['chapters_total']}\n"
        f"Chapters with < 6 items : {len(low_chs)}\n"
        f"Total NEET/PCB resources: {m['entries_published']} ({m['playlists_published']} playlists, {m['videos_published']} lectures)\n"
        f"Queries (Cached / Live) : {m['queries_executed']} ({m['cached_requests']} cached, {m['live_requests']} live)\n"
        f"Distinct NEET institutes: {m['distinct_institutes']}\n"
        f"Distinct NEET educators : {m['distinct_educators']} ({m['distinct_channels']} verified channels)\n"
        f"Subject Breakdown:\n{subj_lines}\n"
        f"Language Breakdown ({len(lang_counts)} languages):\n{lang_lines}\n"
        f"Target Exam Breakdown:\n{exam_lines}\n"
        f"Institute Breakdown:\n{inst_lines}\n"
        f"Output written to       : {OUT_PATH}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
