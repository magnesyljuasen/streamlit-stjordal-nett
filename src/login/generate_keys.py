import streamlit_authenticator as stauth

hashed_passwords = stauth.Hasher(['GRUNNVARME123']).generate()
print(hashed_passwords)