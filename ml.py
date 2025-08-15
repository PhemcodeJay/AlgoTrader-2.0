import os
import json
import numpy as np
import pandas as pd
import joblib
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split

from dotenv import load_dotenv
load_dotenv()  # Load DATABASE_URL from .env

from db import db  # Requires DATABASE_URL to be loaded

# === Configuration Paths ===
MODEL_PATH = "ml_models/profit_xgb_model.pkl"
SIGNAL_EXPORT_PATH = "reports/signals/"
TRADE_EXPORT_PATH = "reports/trades/"


class MLFilter:
    def __init__(self):
        self.model = self._load_model()
        self.db = db

    def _load_model(self):
        if os.path.exists(MODEL_PATH):
            print("[ML] ✅ Loaded trained model.")
            return joblib.load(MODEL_PATH)
        else:
            print("[ML] ⚠️ No trained model found. Using fallback scoring.")
            return None

    def extract_features(self, signal: dict) -> np.ndarray:
        return np.array([
            signal.get("entry", 0),
            signal.get("tp", 0),
            signal.get("sl", 0),
            signal.get("trail", 0),
            signal.get("score", 0),
            signal.get("confidence", 0),
            1 if signal.get("side") == "LONG" else 0,
            1 if signal.get("trend") == "Up" else -1 if signal.get("trend") == "Down" else 0,
            1 if signal.get("regime") == "Breakout" else 0,
        ])

    def enhance_signal(self, signal: dict) -> dict:
        # ML scoring
        if self.model:
            features = self.extract_features(signal).reshape(1, -1)
            prob = self.model.predict_proba(features)[0][1]
            signal["score"] = round(prob * 100, 2)
            signal["confidence"] = int(min(signal["score"] + np.random.uniform(0, 10), 100))
        else:
            signal["score"] = signal.get("score", np.random.uniform(50, 75))
            signal["confidence"] = int(min(signal["score"] + np.random.uniform(5, 20), 100))

        # Margin USDT calculation
        try:
            entry_raw = signal.get("entry") or signal.get("Entry")
            entry_price = float(entry_raw) if entry_raw is not None else 0.0

            leverage_raw = signal.get("leverage", 20)
            leverage = int(leverage_raw) if leverage_raw is not None else 20

            capital_raw = signal.get("capital", 100)
            capital = float(capital_raw) if capital_raw is not None else 100.0

            if entry_price > 0 and leverage > 0:
                margin = capital / leverage
                signal["margin_usdt"] = round(margin, 2)
            else:
                signal["margin_usdt"] = None
        except (TypeError, ValueError):
            signal["margin_usdt"] = None

        return signal


    def migrate_signals_to_json(self):
        os.makedirs(SIGNAL_EXPORT_PATH, exist_ok=True)
        signals = self.db.get_signals(limit=500)

        count = 0
        for sig in signals:
            try:
                sig_dict = sig.to_dict()
                if "id" not in sig_dict or "symbol" not in sig_dict:
                    print(f"[ML] ⚠️ Skipping signal with missing 'id' or 'symbol': {sig_dict}")
                    continue

                filename = os.path.join(SIGNAL_EXPORT_PATH, f"{sig_dict['id']}_{sig_dict['symbol']}.json")
                with open(filename, "w") as f:
                    json.dump(sig_dict, f, indent=2, default=str)
                count += 1
            except Exception as e:
                print(f"[ML] ⚠️ Failed to export signal: {e}")

        print(f"[ML] ✅ Exported {count} signals to {SIGNAL_EXPORT_PATH}")

    def migrate_trades_to_json(self):
        os.makedirs(TRADE_EXPORT_PATH, exist_ok=True)
        trades = self.db.get_trades(limit=500)

        count = 0
        for trade in trades:
            try:
                trade_dict = trade.to_dict()
                entry = trade_dict.get("entry")
                exit_ = trade_dict.get("exit")
                side = trade_dict.get("side")

                if entry is not None and exit_ is not None and side:
                    direction = 1 if side == "LONG" else -1
                    trade_dict["profit"] = 1 if direction * (exit_ - entry) > 0 else 0
                else:
                    trade_dict["profit"] = 0

                if "id" not in trade_dict or "symbol" not in trade_dict:
                    print(f"[ML] ⚠️ Skipping trade with missing 'id' or 'symbol': {trade_dict}")
                    continue

                filename = os.path.join(TRADE_EXPORT_PATH, f"{trade_dict['id']}_{trade_dict['symbol']}.json")
                with open(filename, "w") as f:
                    json.dump(trade_dict, f, indent=2, default=str)
                count += 1
            except Exception as e:
                print(f"[ML] ⚠️ Failed to export trade: {e}")

        print(f"[ML] ✅ Exported {count} trades to {TRADE_EXPORT_PATH}")

    def load_all_trades_from_exports(self) -> list:
        all_trades = []

        trade_files = [f for f in os.listdir(TRADE_EXPORT_PATH) if f.endswith(".json")]
        for file in trade_files:
            try:
                with open(os.path.join(TRADE_EXPORT_PATH, file)) as f:
                    trade = json.load(f)
                    all_trades.append(trade)
            except Exception as e:
                print(f"[ML] ⚠️ Failed to load trade {file}: {e}")

        signal_files = [f for f in os.listdir(SIGNAL_EXPORT_PATH) if f.endswith(".json")]
        for file in signal_files:
            try:
                with open(os.path.join(SIGNAL_EXPORT_PATH, file)) as f:
                    signal = json.load(f)
                    trade = {
                        "symbol": signal.get("symbol"),
                        "entry": signal.get("entry"),
                        "tp": signal.get("tp"),
                        "sl": signal.get("sl"),
                        "trail": signal.get("trail", 0),
                        "score": signal.get("score"),
                        "confidence": signal.get("confidence"),
                        "side": signal.get("side"),
                        "trend": signal.get("trend"),
                        "regime": signal.get("regime", "Breakout"),
                        "profit": 1 if signal.get("score", 0) > 70 else 0
                    }
                    if all(k in trade and trade[k] is not None for k in ["entry", "tp", "sl", "score", "confidence", "side", "trend"]):
                        all_trades.append(trade)
            except Exception as e:
                print(f"[ML] ⚠️ Failed to load signal {file}: {e}")

        print(f"[ML] ✅ Loaded {len(all_trades)} combined trades for training.")
        return all_trades

    def train_from_history(self):
        all_trades = self.load_all_trades_from_exports()
        df = pd.DataFrame(all_trades)

        if df.empty or len(df) < 30:
            print(f"[ML] ❌ Not enough data to train. Found only {len(df)} records.")
            return

        df["side_enc"] = df["side"].map({"LONG": 1, "SHORT": 0}).fillna(0).astype(int)
        df["trend_enc"] = df["trend"].map({"Up": 1, "Down": -1, "Neutral": 0}).fillna(0).astype(int)
        df["regime_enc"] = df["regime"].map({"Breakout": 1, "Mean": 0}).fillna(0).astype(int)

        required_cols = ["entry", "tp", "sl", "trail", "score", "confidence", "side_enc", "trend_enc", "regime_enc"]
        if not all(col in df.columns for col in required_cols):
            print("[ML] ❌ Missing columns. Check your data structure.")
            return

        X = df[required_cols]
        y = df["profit"]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        model = XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            use_label_encoder=False,
            eval_metric="logloss"
        )
        model.fit(X_train, y_train)

        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

        try:
            joblib.dump(model, MODEL_PATH)
            print(f"[ML] ✅ Model saved to {MODEL_PATH}")
        except Exception as e:
            print(f"[ML] ❌ Failed to save model: {e}")

        self.model = model
        acc = model.score(X_test, y_test)
        print(f"[ML] ✅ Trained model on {len(df)} records. Accuracy: {acc:.2%}")


# === CLI Entrypoint ===
if __name__ == "__main__":
    ml = MLFilter()
    ml.migrate_signals_to_json()
    ml.migrate_trades_to_json()
    ml.train_from_history()
