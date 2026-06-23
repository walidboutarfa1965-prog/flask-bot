# -*- coding: utf-8 -*-
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ البوت شغال ومتصل بنجاح!"

@app.route('/health')
def health():
    return "✅ البوت يعمل بشكل صحي", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
