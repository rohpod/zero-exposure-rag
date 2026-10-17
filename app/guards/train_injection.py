import csv
import pickle
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "injection_raw"
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"


def load_data():
    texts, labels = [], []

    # deepset dataset: label column is 0 (safe) / 1 (injection)
    deepset_path = DATA_DIR / "deepset_prompt_injections.csv"
    with open(deepset_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            texts.append(row["text"])
            labels.append("injection" if row["label"] == "1" else "safe")

    # our own benign banking queries: label column already says "safe"
    benign_path = DATA_DIR / "benign_banking_queries.csv"
    with open(benign_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            texts.append(row["text"])
            labels.append(row["label"])

    return texts, labels


def main():
    texts, labels = load_data()
    print(f"Loaded {len(texts)} total examples")
    print(f"  injection: {labels.count('injection')}")
    print(f"  safe:      {labels.count('safe')}")

    X_train, X_val, y_train, y_val = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), max_features=5000)
    X_train_vec = vectorizer.fit_transform(X_train)
    X_val_vec = vectorizer.transform(X_val)

    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train_vec, y_train)

    y_pred = clf.predict(X_val_vec)
    print("\nValidation results:")
    print(classification_report(y_val, y_pred))

    MODEL_DIR.mkdir(exist_ok=True)
    with open(MODEL_DIR / "injection_classifier.pkl", "wb") as f:
        pickle.dump(clf, f)
    with open(MODEL_DIR / "injection_vectorizer.pkl", "wb") as f:
        pickle.dump(vectorizer, f)

    print(f"\nSaved model + vectorizer to {MODEL_DIR}")


if __name__ == "__main__":
    main()
