CLASSES = ("akiec", "bcc", "bkl", "df", "mel", "nv", "vasc")
HIGH_RISK = {"akiec", "bcc", "mel"}
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
IMAGE_SIZE = 224

UNCERTAIN_MAX = 0.40   # best class below this -> model unsure -> retake / clinician
HIGH_RISK_SUM = 0.60   # high-risk classes together; must be above chance level (3/7 ≈ 0.43)


def risk_from_probabilities(probabilities, classes=CLASSES):
    """Map class probabilities to a triage decision.

    Order matters:
      1. Confident high-risk top prediction        -> high
      2. Model unsure overall (low top confidence) -> uncertain (retake photo / clinician review)
      3. High-risk classes clearly dominate        -> high
      4. Otherwise                                 -> low
    The summed threshold is set above the chance level (3 of 7 classes ≈ 0.43),
    so an unsure, near-uniform prediction is not wrongly flagged as high risk.
    """
    pairs = sorted(zip(classes, probabilities), key=lambda item: item[1], reverse=True)
    if not pairs:
        return {"risk_level": "uncertain", "triage_effect": "retake_photo"}

    top_code, top_prob = pairs[0]
    high_sum = sum(prob for code, prob in pairs if code in HIGH_RISK)

    if top_code in HIGH_RISK and top_prob >= TOP1_HIGH:
        return {"risk_level": "high", "triage_effect": "raise_priority"}
    if top_prob < UNCERTAIN_MAX:
        return {"risk_level": "uncertain", "triage_effect": "retake_photo"}
    if high_sum >= HIGH_RISK_SUM:
        return {"risk_level": "high", "triage_effect": "raise_priority"}
    return {"risk_level": "low", "triage_effect": "no_change"}
