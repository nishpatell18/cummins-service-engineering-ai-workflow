"""
scripts/train_assignment_model.py

Generates 500 synthetic historical assignment records with realistic patterns,
trains a Random Forest classifier to predict first-time fix and SLA compliance,
and saves the model to models/assignment_model.pkl

Run once before starting the server:
  python scripts/train_assignment_model.py

REALISTIC PATTERNS BUILT INTO THE DATA:
  - Senior techs (level 3) with system experience have higher FTF rates
  - Proximity matters more for P1 faults (tight SLA)
  - Overloaded techs (2+ active tickets) breach SLA more often
  - Techs without system specialization have lower success rates
  - Junior techs (level 1) assigned to P1 faults fail SLA frequently
  - Experience (years) improves outcomes but with diminishing returns
"""

import json
import os
import sys
import pickle
import random
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
from datetime import datetime

random.seed(42)
np.random.seed(42)

# ── CONSTANTS ─────────────────────────────────────────────────────────────

FAULT_SYSTEMS = ['DEF', 'DPF', 'EGR', 'Fuel', 'Cooling', 'Oil', 'Turbo', 'MAF']

SYSTEM_PRIORITY = {
    'Oil': 1, 'Cooling': 2, 'Fuel': 3, 'Turbo': 4,
    'EGR': 5, 'DPF': 6, 'DEF': 7, 'MAF': 8,
}

# P1 faults need resolution within 2h, P2 within 8h, P3 within 24h
PRIORITY_SLA = {1: 2, 2: 8, 3: 24}

# Minimum cert level required per fault priority
MIN_CERT_FOR_PRIORITY = {1: 2, 2: 1, 3: 1}


# ── SYNTHETIC DATA GENERATOR ──────────────────────────────────────────────

def generate_record():
    """
    Generate one synthetic assignment record with realistic outcome.
    All patterns are engineered to reflect real-world field service dynamics.
    """
    # Fault characteristics
    fault_system   = random.choice(FAULT_SYSTEMS)
    fault_priority = SYSTEM_PRIORITY[fault_system]
    # Simplify to P1/P2/P3
    if fault_priority <= 2:
        priority_class = 1
    elif fault_priority <= 5:
        priority_class = 2
    else:
        priority_class = 3

    sla_hours = PRIORITY_SLA[priority_class]

    # Tech characteristics
    cert_level       = random.choices([1, 2, 3], weights=[30, 45, 25])[0]
    years_experience = random.randint(1, 15)
    proximity_km     = random.uniform(2, 80)
    active_tickets   = random.choices([0, 1, 2, 3], weights=[50, 30, 15, 5])[0]
    has_specialization = random.random() < (0.9 if cert_level == 3 else 0.6 if cert_level == 2 else 0.3)

    # Prior experience with this specific fault system
    if has_specialization:
        prior_experience = random.randint(1, 15)
        prior_success_rate = random.uniform(0.70, 1.0)
    else:
        prior_experience = random.randint(0, 3)
        prior_success_rate = random.uniform(0.30, 0.75)

    # Shift match (tech is on their regular shift)
    shift_match = random.random() < 0.75

    # ── OUTCOME CALCULATION ──────────────────────────────────────────────
    # Base probability of first-time fix
    # Engineered patterns:
    #   Cert level:           strong positive effect
    #   System experience:    strong positive effect
    #   Prior success rate:   strong positive effect
    #   Proximity:            moderate negative effect (far = more rushed)
    #   Active tickets:       moderate negative effect
    #   Shift match:          small positive effect

    base_ftf = 0.50

    # Cert level contribution
    cert_bonus = {1: -0.20, 2: 0.05, 3: 0.20}[cert_level]

    # Experience contribution (diminishing returns above 5 years)
    exp_bonus = min(years_experience * 0.015, 0.15)

    # System specialization
    spec_bonus = 0.15 if has_specialization else -0.10

    # Prior success rate on this system (most important feature)
    hist_bonus = (prior_success_rate - 0.6) * 0.5

    # Proximity penalty (normalized 0-80km)
    prox_penalty = -(proximity_km / 80) * 0.10

    # Workload penalty
    workload_penalty = {0: 0.0, 1: -0.05, 2: -0.12, 3: -0.20}[active_tickets]

    # Shift bonus
    shift_bonus = 0.05 if shift_match else -0.05

    # Priority mismatch penalty (junior tech on P1 fault)
    if priority_class == 1 and cert_level == 1:
        priority_mismatch = -0.30
    elif priority_class == 1 and cert_level == 2:
        priority_mismatch = 0.0
    else:
        priority_mismatch = 0.05

    ftf_prob = base_ftf + cert_bonus + exp_bonus + spec_bonus + hist_bonus \
               + prox_penalty + workload_penalty + shift_bonus + priority_mismatch

    # Clip to [0.05, 0.98]
    ftf_prob = max(0.05, min(0.98, ftf_prob))

    # Add noise
    ftf_prob += random.uniform(-0.05, 0.05)
    ftf_prob = max(0.05, min(0.98, ftf_prob))

    first_time_fix = 1 if random.random() < ftf_prob else 0

    # SLA outcome — correlated with FTF but also proximity matters more
    # Close tech + available + right skills = more likely to meet SLA
    sla_base = ftf_prob * 0.9

    # Proximity has stronger effect on SLA than on FTF (travel time)
    sla_prox_penalty = -(proximity_km / 80) * 0.20

    # P1 with any workload is risky for SLA
    if priority_class == 1 and active_tickets >= 1:
        sla_workload = -0.15
    else:
        sla_workload = workload_penalty

    sla_prob = sla_base + sla_prox_penalty + sla_workload
    sla_prob = max(0.05, min(0.98, sla_prob))
    sla_prob += random.uniform(-0.05, 0.05)
    sla_prob = max(0.05, min(0.98, sla_prob))

    met_sla = 1 if random.random() < sla_prob else 0

    return {
        # Features
        'cert_level':             cert_level,
        'years_experience':       years_experience,
        'proximity_km':           round(proximity_km, 1),
        'active_tickets':         active_tickets,
        'has_specialization':     int(has_specialization),
        'prior_experience':       prior_experience,
        'prior_success_rate':     round(prior_success_rate, 3),
        'shift_match':            int(shift_match),
        'fault_priority':         priority_class,
        'fault_system_encoded':   FAULT_SYSTEMS.index(fault_system),
        'sla_hours':              sla_hours,
        'priority_cert_match':    int(cert_level >= MIN_CERT_FOR_PRIORITY[priority_class]),
        # Targets
        'first_time_fix':         first_time_fix,
        'met_sla':                met_sla,
        # Metadata (not used as features)
        'fault_system':           fault_system,
        'fault_priority_class':   priority_class,
    }


def generate_dataset(n: int = 500) -> pd.DataFrame:
    print(f"[DataGen] Generating {n} synthetic assignment records...")
    records = [generate_record() for _ in range(n)]
    df = pd.DataFrame(records)
    print(f"[DataGen] Done — FTF rate: {df['first_time_fix'].mean():.1%} | "
          f"SLA rate: {df['met_sla'].mean():.1%}")
    return df


# ── FEATURE COLUMNS ───────────────────────────────────────────────────────

FEATURE_COLS = [
    'cert_level',
    'years_experience',
    'proximity_km',
    'active_tickets',
    'has_specialization',
    'prior_experience',
    'prior_success_rate',
    'shift_match',
    'fault_priority',
    'fault_system_encoded',
    'sla_hours',
    'priority_cert_match',
]


# ── TRAINING ──────────────────────────────────────────────────────────────

def train_model(df: pd.DataFrame) -> dict:
    """
    Train two Random Forest classifiers:
      1. Predict first_time_fix (did tech resolve on first visit?)
      2. Predict met_sla (did tech meet SLA?)

    Returns dict with both trained models and metadata.
    """
    X = df[FEATURE_COLS]

    results = {}

    for target in ['first_time_fix', 'met_sla']:
        y = df[target]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            class_weight='balanced'
        )

        model.fit(X_train, y_train)

        # Evaluate
        y_pred    = model.predict(X_test)
        y_prob    = model.predict_proba(X_test)[:, 1]
        accuracy  = accuracy_score(y_test, y_pred)
        cv_scores = cross_val_score(model, X, y, cv=5, scoring='accuracy')

        print(f"\n[Model] Target: {target}")
        print(f"  Test accuracy:  {accuracy:.3f}")
        print(f"  CV accuracy:    {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
        print(f"  Class balance:  {y.value_counts().to_dict()}")

        # Feature importance
        importances = sorted(
            zip(FEATURE_COLS, model.feature_importances_),
            key=lambda x: x[1], reverse=True
        )
        print(f"  Top features:")
        for feat, imp in importances[:5]:
            print(f"    {feat}: {imp:.3f}")

        results[target] = {
            'model':    model,
            'accuracy': accuracy,
            'cv_mean':  cv_scores.mean(),
            'cv_std':   cv_scores.std(),
        }

    return results


# ── SAVE ──────────────────────────────────────────────────────────────────

def save_artifacts(df: pd.DataFrame, results: dict):
    os.makedirs('models', exist_ok=True)

    # Save models
    artifact = {
        'ftf_model':         results['first_time_fix']['model'],
        'sla_model':         results['met_sla']['model'],
        'feature_cols':      FEATURE_COLS,
        'fault_systems':     FAULT_SYSTEMS,
        'trained_at':        datetime.now().isoformat(),
        'training_samples':  len(df),
        'ftf_accuracy':      results['first_time_fix']['accuracy'],
        'sla_accuracy':      results['met_sla']['accuracy'],
        'ftf_cv_mean':       results['first_time_fix']['cv_mean'],
        'sla_cv_mean':       results['met_sla']['cv_mean'],
        'note': (
            'Trained on synthetic data for prototype. '
            'In production: retrain monthly on real assignment outcomes.'
        )
    }

    model_path = os.path.join('models', 'assignment_model.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump(artifact, f)

    print(f"\n[Save] Model saved to {model_path}")

    # Save training data for transparency / audit
    data_path = os.path.join('data', 'assignment_training_data.csv')
    df.to_csv(data_path, index=False)
    print(f"[Save] Training data saved to {data_path}")

    # Save model card
    card = {
        'model_type':        'RandomForestClassifier (scikit-learn)',
        'targets': {
            'first_time_fix': 'Will the tech resolve the fault on the first visit?',
            'met_sla':        'Will the tech meet the SLA deadline?'
        },
        'features':          FEATURE_COLS,
        'training_samples':  len(df),
        'data_source':       'Synthetic — generated with engineered patterns',
        'trained_at':        artifact['trained_at'],
        'performance': {
            'ftf_test_accuracy':  round(results['first_time_fix']['accuracy'], 3),
            'ftf_cv_accuracy':    round(results['first_time_fix']['cv_mean'], 3),
            'sla_test_accuracy':  round(results['met_sla']['accuracy'], 3),
            'sla_cv_accuracy':    round(results['met_sla']['cv_mean'], 3),
        },
        'production_note': (
            'In production this model would be retrained monthly on real '
            'assignment outcome data from the fleet. Features and architecture '
            'remain the same — only training data changes.'
        ),
        'license': 'scikit-learn BSD license — commercial use permitted'
    }

    card_path = os.path.join('models', 'model_card.json')
    with open(card_path, 'w') as f:
        json.dump(card, f, indent=2)
    print(f"[Save] Model card saved to {card_path}")


# ── MAIN ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("Assignment Model Training")
    print("=" * 60)

    # Must run from backend directory
    if not os.path.exists('data'):
        print("ERROR: Run this script from the backend directory:")
        print("  cd buildv6")
        print("  python scripts/train_assignment_model.py")
        sys.exit(1)

    # Generate data
    df = generate_dataset(n=500)

    # Train models
    print("\n[Training] Fitting Random Forest classifiers...")
    results = train_model(df)

    # Save
    save_artifacts(df, results)

    print("\n" + "=" * 60)
    print("Training complete.")
    print(f"  FTF model accuracy:  {results['first_time_fix']['accuracy']:.1%}")
    print(f"  SLA model accuracy:  {results['met_sla']['accuracy']:.1%}")
    print("\nNext: python main.py")
    print("=" * 60)
