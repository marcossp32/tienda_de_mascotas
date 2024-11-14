from flask import Flask, jsonify, request, abort

app = Flask(__name__)

# 7.1 Búsqueda general
@app.route('/api/search', methods=['GET'])
def general_search():
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
