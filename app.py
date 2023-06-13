from flask import Flask, request, jsonify
from llama_index import GPTVectorStoreIndex, SimpleDirectoryReader, StorageContext, load_index_from_storage, LLMPredictor, ServiceContext
import os
import logging
import sys
import uuid
import json
from langchain import OpenAI
from flask_cors import CORS # Import the library
import requests
from dotenv import load_dotenv
import openai
import re

app = Flask(__name__)
CORS(app)  # Enable CORS for the app

# Set up logging
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

# Replace 'data' with the path to your data folder
DIRECTORY = 'data'
load_dotenv()
# openai.api_key = "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"

# print(openai)

#########   PDF   ############


def generate_voiceover_script(bullet_points, NoOfWordsForVOPerBullet, course_name, directory):
    voiceover_script = {}

    # Iterate through each bullet point
    for i, bullet in enumerate(bullet_points):

        # Create a voice over script for each bullet point
        vo_query = f"Generate a voice-over script with {str(NoOfWordsForVOPerBullet)} words for the following point: {bullet}"
        vo_response, message = execute_query(vo_query, course_name, directory)

        # Save the voice over script for the current bullet point
        voiceover_script[f"Bullet {i+1} Voiceover Script"] = vo_response

    return voiceover_script

def saveSubTopicBullets(topics, course_settings, course_name, directory):
    for i, topic in enumerate(topics):
        subtopics = topic.get("subtopics", [])
        for j, subtopic in enumerate(subtopics):
            subtopic_name = subtopic.get("subtopic_name")
            NoOfBulletsPerSubTopic = course_settings.get("NoOfBulletsPerSubTopic", 0)
            NoOfWordsPerBullet = course_settings.get("NoOfWordsPerBullet", 0)
            NoOfWordsForVOPerBullet = course_settings.get("NoOfWordsForVOPerBullet", 0)
            
            subtopic_summary_query = f"Generate {str(NoOfBulletsPerSubTopic)} points with {str(NoOfWordsPerBullet)} words each, for the following subtopic {subtopic_name}"
            subtopic_summary_response, message = execute_query(subtopic_summary_query, course_name, directory)

            # Extract bullet points from the response
            bullet_points = subtopic_summary_response.split("\n")

            # Generate voice over script for each bullet point
            voiceover_script = generate_voiceover_script(bullet_points, NoOfWordsForVOPerBullet, course_name, directory)

            # Adding the bullet points and the voice over script to the respective subtopic
            topics[i]["subtopics"][j]["subtopic_bullets"] = bullet_points
            topics[i]["subtopics"][j]["subtopic_voiceover_script"] = voiceover_script

    return topics


def save_topics_to_json(response, course_name, directory):
    # Parse the response string into a list of topics
    topics_list = re.split("\d+\.\s", response)
    learning_objectives_query = "Generate 5 Learning objectives for a course made with this book"
    learning_objectives, message = execute_query(learning_objectives_query, course_name, DIRECTORY)
    learning_objective = re.split("\d+\.\s", learning_objectives)[1:]
    # Create the course data dictionary
    course_data = {
        "course_name": course_name,
        "learning_objectives": learning_objective,  # Assuming you will fill this in later
        "topics": [{"topic_name": topic} for topic in topics_list]
    }
    
    # Determine the path to the course directory
    file_directory = os.path.join(directory, course_name)
    
    # Determine the path to the course_data.json file
    json_filepath = os.path.join(file_directory, 'course_data.json')
    
    # Save the course data dictionary to the course_data.json file
    with open(json_filepath, 'w') as f:
        json.dump(course_data, f)
    return course_data


def create_index(directory):
    documents = SimpleDirectoryReader(directory).load_data()
    llm_predictor = LLMPredictor(llm=OpenAI(temperature=0.15, model_name="text-curie-001", max_tokens=1800))
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
    index = GPTVectorStoreIndex.from_documents(documents, service_context=service_context)
    return index

def query_index(index, query):
    query_engine = index.as_query_engine()
    response = query_engine.query(query)
    return response

def create_new_index(file_directory):
    file_index = create_index(file_directory)
    return file_index

def execute_query(query, course_name,directory ):
    # query = kwargs.get("query")
    # course_name = kwargs.get("course_name")
    # directory = kwargs.get("directory")

    if not query or not course_name:
        return None, {"error": "Missing query or filename."}

    file_directory = os.path.join(directory, course_name)
    # rebuild storage context
    storage_context = StorageContext.from_defaults(persist_dir=file_directory)
    # load index
    index = load_index_from_storage(storage_context)

    query_engine = index.as_query_engine()
    response = query_engine.query(query)

    return response.response, {"message": "Query executed successfully.", "response": response.response}



# def get_pdf_filenames(directory):
#     all_files = os.listdir(directory)
#     pdf_files = [filename for filename in all_files if filename.endswith('.pdf')]
#     return pdf_files

@app.route("/")
def hello_world():
    return "Hello world! hi"

# def get_filenames_pptx():
#     filenames = get_pdf_filenames(DIRECTORY)
#     return jsonify({"filenames": filenames})
@app.route('/upload_file', methods=['POST'])
def upload_file_and_get_topics():
    try:
        logging.info("Uploading file...")

        if 'file' not in request.files:
            return jsonify({"error": "Missing file."}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "Empty filename."}), 400

        filename = file.filename
        course_name = request.form['course_name']
        course_settings = request.form.get('course_settings', None)

        if course_settings is None:
            return jsonify({"error": "Missing course settings."}), 400

        # Convert course_settings from JSON format to Python dictionary
        course_settings_dict = json.loads(course_settings)
        
        file_directory = os.path.join(DIRECTORY, course_name)
        filepath = os.path.join(file_directory, f"{course_name}_{str(uuid.uuid4())}.pdf")
        os.makedirs(file_directory, exist_ok=True)
        file.save(filepath)

        # Save course_settings in a JSON file
        with open(os.path.join(file_directory, 'course_settings.json'), 'w') as f:
            json.dump(course_settings_dict, f)

        logging.info("Creating and saving index...")
        file_index = create_new_index(file_directory)

        file_index.storage_context.persist(file_directory)

        logging.info("Getting topics...")
        
        if not course_name:
            return jsonify({"error": "Missing course_name."}), 400

        settings_filepath = os.path.join(file_directory, 'course_settings.json')
        
        if not os.path.exists(settings_filepath):
            return jsonify({"error": "Missing course_settings.json file."}), 400
        
        # Load course settings
        with open(settings_filepath, 'r') as f:
            course_settings = json.load(f)
        course_settings = json.loads(course_settings)

        # Get NoOfTopics from course settings
        NoOfTopics = course_settings.get('NoOfTopics', None)
        if NoOfTopics is None:
            return jsonify({"error": "NoOfTopics not found in course settings."}), 400
        
        # Construct the query string
        query = f"Generate {str(NoOfTopics)} from the documents for a Course made From this Book"  
        
        directory = DIRECTORY

        response, message = execute_query(query, course_name, directory)

        if not response:
            return jsonify("message"), 400

        cdata = save_topics_to_json(response, course_name, directory)

        return jsonify(cdata)

    except Exception as e:
        logging.exception("Error in /upload_file_and_get_topics route")
        return jsonify({"error": str(e)}), 500







@app.route('/query_index', methods=['POST'])
def index_query():
    data = request.get_json()
    query = data.get("query")
    filename = data.get("filename")

    if not query:
        return jsonify({"error": "Missing query."}), 400

    if not filename:
        return jsonify({"error": "Missing filename."}), 400

    file_directory = os.path.join(DIRECTORY, filename)
    # rebuild storage context
    storage_context = StorageContext.from_defaults(persist_dir = file_directory)
    # load index
    index = load_index_from_storage(storage_context)

    query_engine = index.as_query_engine()
    response = query_engine.query(query)

    return jsonify({"message": "Query executed successfully.", "response": response.response})

@app.route('/query_course', methods=['POST'])
def course_query():
    data = request.get_json()
    query=data.get("query")
    course_name=data.get("course_name")
    directory=DIRECTORY

    # Ensure DIRECTORY is defined, or replace DIRECTORY with your desired default directory
    response, message = execute_query(query, course_name, directory)

    if not response:
        return jsonify("message"), 400

    return jsonify(response)


@app.route('/get_topics', methods=['POST'])
def get_topics():
    try:
        data = request.get_json()
        course_name = data.get("course_name")
        
        if not course_name:
            return jsonify({"error": "Missing course_name."}), 400

        file_directory = os.path.join(DIRECTORY, course_name)
        settings_filepath = os.path.join(file_directory, 'course_settings.json')
        
        if not os.path.exists(settings_filepath):
            return jsonify({"error": "Missing course_settings.json file."}), 400
        
        # Load course settings
        with open(settings_filepath, 'r') as f:
            course_settings = json.load(f)
        

        course_settings = json.loads(course_settings)  
        # Get NoOfTopics from course settings
        NoOfTopics = course_settings.get('NoOfTopics', None)
        if NoOfTopics is None:
            return jsonify({"error": "NoOfTopics not found in course settings."}), 400
        
        # Construct the query string
        query = f"Generate {str(NoOfTopics)} from the documents for a Course made From this Book"  
        
        directory=DIRECTORY

    # Ensure DIRECTORY is defined, or replace DIRECTORY with your desired default directory
        response, message = execute_query(query, course_name, directory)

        if not response:
            return jsonify("message"), 400

        cdata = save_topics_to_json(response, course_name, directory)

        return jsonify(cdata)

    except Exception as e:
        logging.exception("Error in /get_topics route")
        return jsonify({"error": str(e)}), 500













@app.route('/saveTopics', methods=['POST'])
def saveTopics():
    try:
        data = request.get_json()
        course_name = data.get("course_name")
        topics = data.get("topics")
        
        if not course_name:
            return jsonify({"error": "Missing course_name."}), 400
        
        if not topics:
            return jsonify({"error": "Missing topics."}), 400

        file_directory = os.path.join(DIRECTORY, course_name)
        settings_filepath = os.path.join(file_directory, 'course_settings.json')
        
        if not os.path.exists(settings_filepath):
            return jsonify({"error": "Missing course_settings.json file."}), 400
        
        # Load course settings
        with open(settings_filepath, 'r') as f:
            course_settings = json.load(f)
        
        course_settings = json.loads(course_settings)
        # Get NoOfSubTopicsPerTopic from course settings
        NoOfSubTopicsPerTopic = course_settings.get('NoOfSubTopicsPerTopic', None)
        if NoOfSubTopicsPerTopic is None:
            return jsonify({"error": "NoOfSubTopicsPerTopic not found in course settings."}), 400
        
        # Construct the query strings
        directory=DIRECTORY
        subtopics = []
        for topic in topics:
            topic_name = topic.get("topic_name", "").strip()
            query = f"Generate {str(NoOfSubTopicsPerTopic)} subtopics from the document for the topic '{topic_name}'"
            response, message = execute_query(query, course_name, directory)
            
            # Convert the response string into a list of subtopics
            response_subtopics = re.split("\d+\.\s", response)
            
            # Transform each subtopic into a dictionary with a key `subtopic_name`
            response_subtopics = [{"subtopic_name": subtopic} for subtopic in response_subtopics]

            # Add the list of subtopics to the current topic dictionary
            topic['subtopics'] = response_subtopics

        # Save the updated topics list with subtopics to course_data.json
        course_data_filepath = os.path.join(file_directory, 'course_data.json')
        with open(course_data_filepath, 'r') as f:
            course_data = json.load(f)
        course_data['topics'] = topics
        with open(course_data_filepath, 'w') as f:
            json.dump(course_data, f)

        return jsonify(course_data)

    except Exception as e:
        logging.exception("Error in /saveTopics route")
        return jsonify({"error": str(e)}), 500













@app.route('/saveSubtopics', methods=['POST'])
def saveSubtopics():
    try:
        data = request.get_json()
        course_name = data.get("course_name")
        topics = data.get("topics")
        
        if not course_name:
            return jsonify({"error": "Missing course_name."}), 400
        
        if not topics:
            return jsonify({"error": "Missing topics."}), 400

        file_directory = os.path.join(DIRECTORY, course_name)
        course_data_filepath = os.path.join(file_directory, 'course_data.json')
        course_settings_filepath = os.path.join(file_directory, 'course_settings.json')
        
        if not os.path.exists(course_data_filepath):
            return jsonify({"error": "Missing course_data.json file."}), 400
        
        if not os.path.exists(course_settings_filepath):
            return jsonify({"error": "Missing coursesettings.json file."}), 400

        # Load course data
        with open(course_data_filepath, 'r') as f:
            course_data = json.load(f)
        
        # Load course settings
        with open(course_settings_filepath, 'r') as f:
            course_settings = json.load(f)
        
        course_settings = json.loads(course_settings)
        topic_summary_queries = []
        topic_summary_voiceover_script_queries = []
        

        directory= DIRECTORY
        for topic in topics:
            topic_name = topic.get("topic_name")
            NoOfWordsPerTopicSummary = course_settings.get("NoOfWordsPerTopicSummary", 0)
            NoOfWordsForVOPerTopicSummary = course_settings.get("NoOfWordsForVOPerTopicSummary", 0)
            
            topic_summary_query = f"Generate a summary in {str(NoOfWordsPerTopicSummary)} words for the following topic {topic_name}"
            topic_summary_response, message = execute_query(topic_summary_query, course_name, directory)
            topic_summary_voiceover_script_query = f"Generate a over script in {str(NoOfWordsForVOPerTopicSummary)} words for the following topic {topic_name}"
            topic_summary_voiceover_script_query_response, message = execute_query(topic_summary_voiceover_script_query, course_name, directory)
            
            for course_topic in course_data.get('topics', []):
                if course_topic.get('topic_name') == topic_name:
                    course_topic['topic_summary'] = topic_summary_response
                    course_topic['topic_summary_voiceover_script'] = topic_summary_voiceover_script_query_response
                    break


        with open(course_data_filepath, 'w') as f:
            json.dump(course_data, f, indent=4)
      
        return jsonify(course_data)

    except Exception as e:
        logging.exception("Error in /saveSubtopics route")
        return jsonify({"error": str(e)}), 500





@app.route('/saveTopicSummary', methods=['POST'])
def saveTopicSummary():
    try:
        data = request.get_json()
        course_name = data.get("course_name")
        topics = data.get("topics")
        
        if not course_name:
            return jsonify({"error": "Missing course_name."}), 400
        
        if not topics:
            return jsonify({"error": "Missing topics."}), 400

        file_directory = os.path.join(DIRECTORY, course_name)
        course_data_filepath = os.path.join(file_directory, 'course_data.json')
        course_settings_filepath = os.path.join(file_directory, 'course_settings.json')
        
        if not os.path.exists(course_data_filepath):
            return jsonify({"error": "Missing course_data.json file."}), 400
        
        if not os.path.exists(course_settings_filepath):
            return jsonify({"error": "Missing coursesettings.json file."}), 400

        # Load course data
        with open(course_data_filepath, 'r') as f:
            course_data = json.load(f)
        
        # Load course settings
        with open(course_settings_filepath, 'r') as f:
            course_settings = json.load(f)
        course_settings = json.loads(course_settings)
        directory= DIRECTORY

        topics = saveSubTopicBullets(topics, course_settings, course_name, directory)
        for new_topic in topics:
            for old_topic in course_data["topics"]:
                if new_topic["topic_name"] == old_topic["topic_name"]:
                    old_topic["subtopics"] = new_topic["subtopics"]

        # Save updated course data back to the course_data.json file
        with open(course_data_filepath, 'w') as f:
            json.dump(course_data, f, indent=4)
       
        return jsonify({"message": course_data}), 200

    except Exception as e:
        logging.exception("Error in /saveTopicSummary route")
        return jsonify({"error": str(e)}), 500











if __name__ == '__main__':
    app.run(debug=True)



