"""
ETAP-AI-WORK Revit Integration APS Auth Service
===============================================

Authentication service for Autodesk Platform Services.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import asyncio
import aiohttp
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt


@dataclass
class APSToken:
    """Represents an APS access token."""
    access_token: str
    refresh_token: Optional[str]
    expires_in: int
    token_type: str
    scope: str
    issued_at: datetime


class APSAuthService:
    """
    Authentication service for Autodesk Platform Services.
    Handles 3-legged OAuth and 2-legged authentication.
    """
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = "https://developer.api.autodesk.com"
        self.token_url = f"{self.base_url}/authentication/v2/token"
        self.refresh_url = f"{self.base_url}/authentication/v2/refresh"
        self.logger = logging.getLogger(__name__)
        self._access_token: Optional[APSToken] = None
    
    async def authenticate_two_legged(self, scopes: list = None) -> Optional[APSToken]:
        """
        Authenticate using 2-legged OAuth (app-to-app).
        
        Args:
            scopes: List of required scopes
            
        Returns:
            APSToken: Authentication token or None if failed
        """
        if scopes is None:
            scopes = ['data:read', 'data:write', 'data:create', 'bucket:read', 'bucket:create']
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials',
            'scope': ' '.join(scopes)
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_url, headers=headers, data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self._access_token = APSToken(
                            access_token=token_data['access_token'],
                            refresh_token=None,
                            expires_in=token_data['expires_in'],
                            token_type=token_data['token_type'],
                            scope=token_data['scope'],
                            issued_at=datetime.utcnow()
                        )
                        self.logger.info("Successfully authenticated with 2-legged OAuth")
                        return self._access_token
                    else:
                        self.logger.error(f"Authentication failed: {response.status}")
                        return None
        except Exception as e:
            self.logger.error(f"Error during 2-legged authentication: {e}")
            return None
    
    async def get_access_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            str: Valid access token or None if authentication failed
        """
        if self._access_token is None:
            # Try to authenticate
            token = await self.authenticate_two_legged()
            return token.access_token if token else None
        
        # Check if token is expired
        expiry_time = self._access_token.issued_at + timedelta(seconds=self._access_token.expires_in)
        if datetime.utcnow() >= expiry_time:
            # Token expired, need to refresh or re-authenticate
            if self._access_token.refresh_token:
                # Refresh token (for 3-legged auth)
                refreshed_token = await self._refresh_token(self._access_token.refresh_token)
                return refreshed_token.access_token if refreshed_token else None
            else:
                # Re-authenticate (for 2-legged auth)
                token = await self.authenticate_two_legged()
                return token.access_token if token else None
        
        return self._access_token.access_token
    
    async def _refresh_token(self, refresh_token: str) -> Optional[APSToken]:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Refresh token to use
            
        Returns:
            APSToken: New access token or None if failed
        """
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.refresh_url, headers=headers, data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self._access_token = APSToken(
                            access_token=token_data['access_token'],
                            refresh_token=token_data.get('refresh_token'),  # May not be provided
                            expires_in=token_data['expires_in'],
                            token_type=token_data['token_type'],
                            scope=token_data['scope'],
                            issued_at=datetime.utcnow()
                        )
                        self.logger.info("Successfully refreshed access token")
                        return self._access_token
                    else:
                        self.logger.error(f"Token refresh failed: {response.status}")
                        return None
        except Exception as e:
            self.logger.error(f"Error during token refresh: {e}")
            return None
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests.
        
        Returns:
            Dict[str, str]: Authentication headers
        """
        token = asyncio.run(self.get_access_token()) if self._access_token else None
        if token:
            return {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
        else:
            return {
                'Content-Type': 'application/json'
            }


class APSConfig:
    """
    Configuration class for APS integration.
    Stores credentials and configuration parameters.
    """
    
    def __init__(self):
        self.client_id = ""
        self.client_secret = ""
        self.bucket_key = ""
        self.region = "US"
        self.scopes = ['data:read', 'data:write', 'data:create', 'bucket:read', 'bucket:create']
        self.logger = logging.getLogger(__name__)
    
    def load_from_env(self):
        """Load configuration from environment variables."""
        import os
        self.client_id = os.getenv('APS_CLIENT_ID', '')
        self.client_secret = os.getenv('APS_CLIENT_SECRET', '')
        self.bucket_key = os.getenv('APS_BUCKET_KEY', '')
        self.region = os.getenv('APS_REGION', 'US')
        
        if not all([self.client_id, self.client_secret]):
            self.logger.warning("APS credentials not found in environment variables")
    
    def is_configured(self) -> bool:
        """Check if APS is properly configured."""
        return all([self.client_id, self.client_secret])