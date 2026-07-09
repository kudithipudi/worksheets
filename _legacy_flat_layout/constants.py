"""
Curriculum constants for the Texas Worksheet Generator.
All VALID_* lists and TOPICS_BY_SUBJECT drawn from official Texas TEKS documents.
"""

VALID_GRADES: list[str] = [
    "Pre-K", "Kindergarten",
    "Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5",
    "Grade 6", "Grade 7", "Grade 8",
    "Grade 9", "Grade 10", "Grade 11", "Grade 12",
]

VALID_SUBJECTS: list[str] = [
    "Mathematics",
    "Reading & ELA",
    "Science",
    "Social Studies",
    "Writing",
]

# Strand names drawn directly from the published Texas TEKS documents.
TOPICS_BY_SUBJECT: dict[str, list[str]] = {
    "Mathematics": [
        "Number and Operations",
        "Algebraic Reasoning",
        "Geometry and Measurement",
        "Data Analysis",
        "Proportionality",
        "Financial Literacy",
    ],
    "Reading & ELA": [
        "Foundational Language Skills",
        "Reading Comprehension",
        "Author's Purpose and Craft",
        "Vocabulary",
        "Literary Analysis",
        "Research and Inquiry",
    ],
    "Science": [
        "Matter and Energy",
        "Force, Motion, and Energy",
        "Earth and Space",
        "Organisms and Environments",
    ],
    "Social Studies": [
        "History",
        "Geography",
        "Economics",
        "Government and Citizenship",
        "Culture and Society",
    ],
    "Writing": [
        "Personal Narrative",
        "Expository Writing",
        "Persuasive / Argumentative Writing",
        "Informational Writing",
        "Research Writing",
    ],
}

VALID_LEVELS: list[str] = ["Approaching", "On-Level", "Advanced", "GT/Enrichment"]

VALID_QUESTION_TYPES: list[str] = [
    "Multiple Choice", "Short Answer", "Fill-in-the-Blank",
    "Matching", "True/False", "Mixed",
]

FLAG_THRESHOLD: int = 5
