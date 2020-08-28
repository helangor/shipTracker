from app import app

app.config['ENV'] = 'development'
app.config['DEBUG'] = True
app.config['TESTING'] = True

if __name__ == "__main__":
    app.run()

