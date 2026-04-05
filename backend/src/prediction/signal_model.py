"""Trained signal model for BUY/SELL/HOLD predictions."""

import pickle
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, confusion_matrix
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class SignalModel:
    """
    Trained machine learning model for signal generation.
    
    Features:
      - spread
      - mid_price (normalized by starting price)
      - order_book_imbalance
      - trade_flow
      - volatility
      - inventory
    
    Output: Probability distribution over {BUY, SELL, HOLD}
    """
    
    FEATURES = ["spread", "mid_price", "order_book_imbalance", "trade_flow", "volatility", "inventory"]
    LABEL_ENCODE = {"BUY": 2, "SELL": 0, "HOLD": 1}
    LABEL_DECODE = {v: k for k, v in LABEL_ENCODE.items()}
    
    def __init__(self):
        self.model: Optional[LogisticRegression] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False
    
    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> Dict[str, Any]:
        """
        Train logistic regression on features and labels.
        
        Args:
            X: DataFrame with feature columns
            y: Series with labels (BUY/SELL/HOLD)
            test_size: Fraction for test set
            random_state: Random seed
            
        Returns:
            Dictionary with training metrics (precision, recall, f1)
        """
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("scikit-learn not installed. Install via: pip install scikit-learn")
        
        # Encode labels
        y_encoded = y.map(self.LABEL_ENCODE)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_encoded, test_size=test_size, random_state=random_state, stratify=y_encoded
        )
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        self.model = LogisticRegression(
            max_iter=1000,
            random_state=random_state,
            solver="lbfgs",
            class_weight="balanced",  # Handle class imbalance
        )
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        train_score = self.model.score(X_train_scaled, y_train)
        test_score = self.model.score(X_test_scaled, y_test)
        y_pred = self.model.predict(X_test_scaled)
        
        self.is_trained = True
        
        # Generate report
        report_dict = classification_report(
            y_test, y_pred,
            target_names=list(self.LABEL_DECODE.values()),
            output_dict=True,
        )
        
        return {
            "train_accuracy": float(train_score),
            "test_accuracy": float(test_score),
            "classification_report": report_dict,
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "n_features": len(self.FEATURES),
            "n_training_samples": len(X_train),
            "n_test_samples": len(X_test),
        }
    
    def predict_proba(self, features: Dict[str, float]) -> Dict[str, float]:
        """
        Predict probability distribution over actions.
        
        Args:
            features: Dict with keys matching FEATURES
            
        Returns:
            Dict {'BUY': P(BUY), 'SELL': P(SELL), 'HOLD': P(HOLD)}
        """
        if not self.is_trained or self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained. Call train() first.")
        
        # Extract and order features
        X = np.array([[features.get(f, 0.0) for f in self.FEATURES]])
        
        # Scale
        X_scaled = self.scaler.transform(X)
        
        # Predict probabilities
        probs = self.model.predict_proba(X_scaled)[0]
        
        return {
            self.LABEL_DECODE[i]: float(probs[i])
            for i in range(len(probs))
        }
    
    def predict(self, features: Dict[str, float]) -> str:
        """
        Get top predicted action.
        
        Args:
            features: Dict with keys matching FEATURES
            
        Returns:
            'BUY', 'SELL', or 'HOLD'
        """
        if not self.is_trained or self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained. Call train() first.")
        
        # Extract and order features
        X = np.array([[features.get(f, 0.0) for f in self.FEATURES]])
        
        # Scale
        X_scaled = self.scaler.transform(X)
        
        # Predict
        pred_encoded = self.model.predict(X_scaled)[0]
        return self.LABEL_DECODE[pred_encoded]
    
    def save(self, filepath: Path) -> None:
        """Save model and scaler to disk."""
        if not self.is_trained:
            raise RuntimeError("Cannot save untrained model.")
        
        checkpoint = {
            "model": self.model,
            "scaler": self.scaler,
            "features": self.FEATURES,
        }
        
        with open(filepath, "wb") as f:
            pickle.dump(checkpoint, f)
        
        print(f"Model saved to {filepath}")
    
    @classmethod
    def load(cls, filepath: Path) -> "SignalModel":
        """Load model and scaler from disk."""
        if not filepath.exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")
        
        with open(filepath, "rb") as f:
            checkpoint = pickle.load(f)
        
        instance = cls()
        instance.model = checkpoint["model"]
        instance.scaler = checkpoint["scaler"]
        instance.is_trained = True
        
        print(f"Model loaded from {filepath}")
        return instance
