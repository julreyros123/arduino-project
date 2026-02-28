from sqlalchemy import Column, Integer, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class ReactionTimeRecord(Base):
    __tablename__ = 'reaction_time_records'

    id = Column(Integer, primary_key=True)
    reaction_time = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ReactionTimeRecord(id={self.id}, reaction_time={self.reaction_time}, timestamp={self.timestamp})>"