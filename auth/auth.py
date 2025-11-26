"""
Authentication module for CDSE platform.

Handles token generation for Copernicus Data Space Ecosystem (CDSE).
"""

import requests
from ..utils.config import (
    CDSE_USERNAME,
    CDSE_PASSWORD,
)
from ..utils.logging import setup_logger

logger = setup_logger("auth")


def get_cdse_token():
    """
    Authenticates with CDSE and retrieves an access token.

    Returns
    -------
    str
        Access token for CDSE API.

    Raises
    ------
    Exception
        If authentication fails.
    """
    logger.info("🔑 Authenticating with CDSE...")
    
    auth_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    
    data = {
        "grant_type": "password",
        "username": CDSE_USERNAME,
        "password": CDSE_PASSWORD,
        "client_id": "cdse-public",
    }
    
    try:
        response = requests.post(auth_url, data=data, timeout=30)
        response.raise_for_status()
        token = response.json()["access_token"]
        logger.info("✅ CDSE authentication successful")
        return token
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ CDSE authentication failed: {e}")
        raise Exception(f"CDSE authentication failed: {e}")


# Alias for backward compatibility
def get_token(platform: str = "cdse"):
    """
    Get authentication token for the specified platform.
    
    Parameters
    ----------
    platform : str
        Platform name. Only 'cdse' is supported.
        
    Returns
    -------
    str
        Access token
    """
    if platform.lower() == "cdse":
        return get_cdse_token()
    else:
        logger.warning(f"Unknown platform: {platform}. Defaulting to CDSE.")
        return get_cdse_token()
