#!/usr/bin/env python3
"""
JWT Token Generator for Yuxi-Know System
"""

import jwt
import json
from datetime import datetime, timedelta
import sys

def generate_jwt_token(user_id: str, username: str, display_name: str = None, organization: str = None):
    """Generate a JWT token for testing purposes"""
    
    # Token payload
    now = datetime.now()
    exp = now + timedelta(days=30)  # 30 days validity
    
    payload = {
        'user_id': user_id,
        'login_name': username,
        'user_name': username,
        'display_name': display_name or username,
        'organization': organization or 'default',
        'region': 'ZB',
        'scope': ['openid'],
        'iss': 'a36c3049b36249a3c9f8891cb127243c',
        'exp': int(exp.timestamp()),
        'iat': int(now.timestamp()),
        'jti': f'test-token-{user_id}',
        'client_id': 'webapp'
    }
    
    # Use a dummy secret for testing (in production this should be a proper secret)
    secret = 'test-secret-key-for-development-only'
    
    # Generate token (using HS256 for simplicity, production would use RS256)
    token = jwt.encode(payload, secret, algorithm='HS256')
    
    return token

def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_jwt_token.py <user_id> <username> [display_name] [organization]")
        print("Example: python generate_jwt_token.py bpaooawkyt2h5g5h9dza7rl3 rf_sjz '瑞飞数据组' 'ORGASZ100011287'")
        sys.exit(1)
    
    user_id = sys.argv[1]
    username = sys.argv[2]
    display_name = sys.argv[3] if len(sys.argv) > 3 else None
    organization = sys.argv[4] if len(sys.argv) > 4 else None
    
    token = generate_jwt_token(user_id, username, display_name, organization)
    
    print(f"\nGenerated JWT Token for user '{username}':")
    print(f"User ID: {user_id}")
    print(f"Username: {username}")
    print(f"Display Name: {display_name or username}")
    print(f"Organization: {organization or 'default'}")
    print(f"\nToken:")
    print(token)
    print(f"\nToken expires in 30 days")
    
    # Also decode and show the payload for verification
    payload = jwt.decode(token, options={"verify_signature": False})
    print(f"\nDecoded payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()