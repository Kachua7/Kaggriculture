"""kagfarm — the Kaggriculture agent. This package is the only thing that ships.

Import rule: dependencies flow one way, from `constants` outward. Nothing in here may
import the mirror simulator (`engine.py`) or anything outside the standard library,
because the Kaggle submission sandbox has neither network nor third-party packages.
"""
