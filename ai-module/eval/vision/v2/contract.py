"""Shared v2.1 evaluation contract constants."""

PROTOCOL_VERSION = "v2.1"
MODEL_PROTOCOL_VERSION = "v2.1-model-consensus"
MODEL_LABEL_SOURCE = "model_consensus"

TOTAL_ITEMS = 160
POSITIVES = 80
NEGATIVES = 80

TEST_ITEMS = 80
TEST_POSITIVES = 40
TEST_NEGATIVES = 40

PER_MAJOR = 10
TEST_PER_MAJOR = 5
PER_CONFUSER_GROUP = 10
TEST_PER_CONFUSER_GROUP = 5

MAJOR_CODES = (
    "traffic",
    "municipal",
    "fire",
    "building",
    "utility",
    "construction",
    "elevator_special",
    "environment_other",
)

ALLOWED_LABEL_SOURCES = frozenset({
    "human_reviewed",
    "human_confirmed_ai_prelabel",
    "legacy_review",
})

