from db.schema.migrate_taxonomy_v2b import TARGET_PATHS
from db.seed.data_cases_v2b import CASES_V2B
from db.seed.data_regulations_v2b import REGULATIONS_V2B


def test_v2b_seed_categories_are_valid_33_class_paths():
    for item in CASES_V2B:
        assert item["category"] in TARGET_PATHS
    for item in REGULATIONS_V2B:
        assert item["category"] in TARGET_PATHS
    assert len(TARGET_PATHS) == 33


def test_v2b_seed_adds_tree_cases_and_regulations_to_reach_minimums():
    tree_cases = [x for x in CASES_V2B if x["category"] == "市政设施/树木倒伏/断枝风险"]
    tree_regs = [x for x in REGULATIONS_V2B if x["category"] == "市政设施/树木倒伏/断枝风险"]
    hazmat_regs = [x for x in REGULATIONS_V2B if x["category"] == "环境与其他/危化品/易燃易爆违规存运"]
    assert len(tree_cases) >= 2
    assert len(tree_regs) >= 2
    assert len(hazmat_regs) >= 1
