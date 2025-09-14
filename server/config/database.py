from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

URL_DATABASE = 'mysql+pymysql://root:@localhost:3306/aivina'

#Create the database engine
engine = create_engine(URL_DATABASE)

#Create a local session for the engine
sessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

base = declarative_base()

def get_db_connection():

    #Try to connect with the session created with the engine
    db = sessionLocal()

    #Yield the db connection, if error close it
    try:
        yield db
    finally:
        db.close()