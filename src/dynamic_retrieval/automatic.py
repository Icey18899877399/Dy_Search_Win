"""Conservative English directional features for five bounded question families.

These deterministic rules are experimental inputs, not verified facts, human
annotations, calibrated probabilities, or outcome labels. Existing evidence
extraction supplies the speculation guard and abstains on conflicting votes.
"""
import re


VERSION = 'automatic-directional-rules-v1'
FIELDS = ('target_elements', 'element_aliases', 'positive_patterns', 'negative_patterns')


def _category(task):
    question = task.get('question', '').strip()
    families = (
        ('regime_fall', r'^Will\s+(?:the\s+)?(.+?)\s+fall\b'),
        ('presidential_nomination', r'^Will\s+(.+?)\s+win\s+(?:the\s+)?(?:\d{4}\s+)?Republican\s+presidential\s+nomination\b'),
        ('french_presidential_election', r'^Will\s+(.+?)\s+win\s+(?:the\s+)?(?:\d{4}\s+)?French\s+presidential\s+election\b'),
        ('nobel_peace_prize', r'^Will\s+(.+?)\s+win\s+(?:the\s+)?Nobel\s+Peace\s+Prize\b'),
        ('israeli_prime_minister', r'^Will\s+(.+?)\s+be\s+(?:the\s+)?next\s+Prime\s+Minister\s+(?:of\s+)?Israel\b'),
    )
    for category, pattern in families:
        match = re.search(pattern, question, re.I)
        if match:
            subject = match.group(1).strip()
            if category == 'regime_fall' and subject.casefold() != 'iranian regime':
                continue
            if not subject or len(subject) > 100 or re.search(r'[?;\n]', subject):
                break
            return category, subject
    raise ValueError('Question is outside the supported automatic rule families')


def _patterns(subjects, actions):
    subject = '(?:' + '|'.join(re.escape(value) for value in subjects) + ')'
    # Restrict to declarative clauses beginning with the target entity. A mention
    # elsewhere in a sentence cannot attribute another person's action to it.
    # Conservative sentence-wide negation/claim guards sacrifice recall.
    guard = r'^(?!.*\b(?:not|never|no|denied?|denies|false|falsely|rumou?r\w*|unconfirmed|alleged\w*)\b)\s*(?:the\s+)?'
    return [guard + subject + r'\s+' + action + r'\b' for action in actions]


def automatic_rules(task):
    """Return only extraction configuration; unsupported question families fail."""
    category, subject = _category(task)
    subjects = [subject]
    if 'É' in subject or 'é' in subject:
        subjects.append(subject.replace('É', 'E').replace('é', 'e'))
    if category == 'regime_fall':
        subjects.extend(["Iran's regime", 'Iran’s regime'])
        action, obj = 'fall', 'power'
        aliases = ['fall', 'fell', 'collapsed', 'toppled', 'overthrown', 'remains', 'retains']
        positive = [r'(?:has\s+)?collapsed', r'(?:has\s+)?fallen', r'fell',
                    r'(?:was|has\s+been)\s+(?:toppled|overthrown)']
        negative = [r'(?:remains|remained)\s+in\s+power', r'(?:retains|retained)\s+power']
    elif category in ('presidential_nomination', 'french_presidential_election'):
        action = 'win'
        obj = ('Republican presidential nomination' if category == 'presidential_nomination'
               else 'French presidential election')
        target = re.escape(obj)
        contest = r'(?:the\s+)?(?:' + target + r'|(?:French\s+|Republican\s+)?presidential\s+(?:race|election|nomination))'
        aliases = ['win', 'won', 'announced', 'declared', 'nominated', 'withdrew', 'disqualified']
        positive = [r'(?:won|wins|has\s+won)\s+(?:the\s+)?' + target,
                    r'(?:announced|declared|has\s+announced|has\s+declared)\s+(?:(?:his|her|their)\s+)?candidacy\s+for\s+' + contest,
                    r'(?:was|has\s+been)\s+nominated\s+for\s+(?:the\s+)?' + target]
        negative = [r'(?:withdrew|has\s+withdrawn)\s+from\s+' + contest,
                    r'(?:was|has\s+been)\s+disqualified\s+from\s+' + contest]
    elif category == 'nobel_peace_prize':
        action, obj = 'win', 'Nobel Peace Prize'
        aliases = ['win', 'won', 'nominated', 'awarded', 'stripped']
        prize = r'(?:the\s+)?Nobel\s+Peace\s+Prize'
        positive = [r'(?:won|wins|has\s+won)\s+' + prize,
                    r'(?:was|has\s+been)\s+nominated\s+for\s+' + prize,
                    r'(?:was|has\s+been)\s+awarded\s+' + prize]
        negative = [r'(?:was|has\s+been)\s+stripped\s+of\s+' + prize]
    else:
        action, obj = 'appointed', 'Prime Minister'
        aliases = ['appointed', 'became', 'becomes', 'withdrew', 'withdrawn']
        office = r'(?:the\s+)?(?:next\s+)?Prime\s+Minister\s+of\s+Israel'
        positive = [r'(?:was|has\s+been)\s+appointed\s+(?:as\s+)?' + office,
                    r'(?:became|becomes|has\s+become)\s+' + office]
        negative = [r'(?:withdrew|has\s+withdrawn)\s+from\s+(?:the\s+)?(?:race|contest)\s+for\s+' + office]
    return dict(target_elements=dict(subject=subject, action=action, object=obj),
                element_aliases=dict(subject=subjects[1:], action=aliases),
                positive_patterns=_patterns(subjects, positive),
                negative_patterns=_patterns(subjects, negative))


def describe_automatic_policy(task):
    """Metadata to record alongside runs without injecting it into extraction."""
    category, subject = _category(task)
    return dict(version=VERSION, category=category, subject=subject,
                mode='deterministic_english_rules', human_reviewed=False,
                support_semantics='mechanical_directional_features_not_outcome_truth',
                limitations=[
                    'Candidacy and nomination are directional proxy features, not final outcomes.',
                    'Rules cannot establish semantic prospectivity or validate the source claim.',
                    'English declarative entity-leading sentences only; low recall is intentional.',
                    'Speculation, sentence negation, and document-level conflicting votes abstain.',
                    'Dates are not matched to the target cycle; historical mentions can match.',
                    'No human annotation, model inference, network access, or label lookup is used.',
                ])
