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
import openai
import re
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)  # Enable CORS for the app

# Set up logging
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

# Replace 'data' with the path to your data folder
DIRECTORY = 'data'

# Load the environment variables from the .env file
load_dotenv()
# Access the API key
os.getenv("OPENAI_API_KEY")

# os.environ['OPENAI_API_KEY'] = "sk-"

#########   PDF   ############


def execute_query(query, course_name,directory ):

    if not query or not course_name:
        return None, {"error": "Missing query or filename."}

    file_directory = os.path.join(directory, course_name)

    # llm_predictor = LLMPredictor(llm=OpenAI(temperature=0.15, model_name="text-curie-001", max_tokens=1800))
    # service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)

    # rebuild storage context
    storage_context = StorageContext.from_defaults(persist_dir=file_directory)
    # load index
    index = load_index_from_storage(storage_context)

    query_engine = index.as_query_engine()
    response = query_engine.query(query)

    return response.response, {"message": "Query executed successfully.", "response": response.response}


def generate_voiceover_script(bullet_text, NoOfWordsForVOPerBullet, course_name, directory):
    vo_query = f"Generate a voice-over script with {NoOfWordsForVOPerBullet} words for the following point: {bullet_text}. Don't include the word 'Voiceover' in the response"
    vo_response, message = execute_query(vo_query, course_name, directory)
    vo_response = vo_response.replace("\n", "").replace("\\", "").replace("\"", "")

    return vo_response

def saveSubTopicBullets(topics, course_settings, course_name, directory):
    for i, topic in enumerate(topics):

        topic_name = topic.get("topic_name")
        NoOfWordsPerTopicSummary = course_settings.get("NoOfWordsPerTopicSummary", 0)
        NoOfWordsForVOPerTopicSummary = course_settings.get("NoOfWordsForVOPerTopicSummary", 0)
        
        topic_summary_query = f"Generate a summary in {str(NoOfWordsPerTopicSummary)} words for the following topic '{topic_name}'"
        topic_summary_response, message = execute_query(topic_summary_query, course_name, directory)
        topic_summary_voiceover_script_query = f"Generate a voice over script in {str(NoOfWordsForVOPerTopicSummary)} words for the following topic of '{topic_name}'"
        topic_summary_voiceover_script_query_response, message = execute_query(topic_summary_voiceover_script_query, course_name, directory)

        if topic_summary_response.startswith('\n'):
            topic_summary_response = topic_summary_response.lstrip('\n')
        
        if topic_summary_voiceover_script_query_response.startswith('\n'):
            topic_summary_voiceover_script_query_response = topic_summary_voiceover_script_query_response.lstrip('\n')

        topic['topic_summary'] = topic_summary_response
        topic['topic_summary_voiceover_script'] = topic_summary_voiceover_script_query_response


        subtopics = topic.get("subtopics", [])
        for j, subtopic in enumerate(subtopics):
            subtopic_name = subtopic.get("subtopic_name")
            # NoOfBulletsPerSubTopic = course_settings.get("NoOfBulletsPerSubTopic", 0)
            NoOfWordsPerBullet = course_settings.get("NoOfWordsPerBullet", 0)
            NoOfWordsForVOPerBullet = course_settings.get("NoOfWordsForVOPerBullet", 0)
            
            # subtopic_summary_query = f"Generate points with {str(NoOfWordsPerBullet)} words each, for the subtopic of '{subtopic_name}'."



            subtopic_summary_query = f"Generate a list of short summary points, that covers the section of '{subtopic_name}'. where each point is ordered with a number, and has excalty {str(NoOfWordsPerBullet)} words per summary point"

            subtopic_summary_response, message = execute_query(subtopic_summary_query, course_name, directory)
            # topics[i]["subtopics"][j]["Direct response"] = subtopic_summary_response

            # Extract bullet points from the response
            # bullet_points = subtopic_summary_response.split("\n")
            # bullet_points = re.split("\n", subtopic_summary_response)[1:]
            # bullet_points = re.split("\d+\.\s", subtopic_summary_response)[1:]
            bullet_points = subtopic_summary_response.split("\n")[1:]

            # bullet_points = re.findall(r'\d+\..*?(?=\n\d+\.|\Z)', subtopic_summary_response, re.DOTALL)
            bullet_points = [{"bullet": bullet} for bullet in bullet_points]
            # bullet_points = subtopic_summary_response
            # [{"topic_name": topic} for topic in topics_list]

            # Adding the bullet points and the voice over script to the respective subtopic
            topics[i]["subtopics"][j]["subtopic_bullets"] = bullet_points

    return topics

def saveSubTopicBulletsWithVO(topics, course_settings, course_name, directory):
    for i, topic in enumerate(topics):
        subtopics = topic.get("subtopics", [])
        topic_name = topic.get("topic_name")
        for j, subtopic in enumerate(subtopics):
            NoOfWordsForVOPerBullet = course_settings.get("NoOfWordsForVOPerBullet", 0)
            bullet_points = subtopic.get("subtopic_bullets", [])
            for bullet in bullet_points:
                bullet["bullet_voiceover"] = generate_voiceover_script(bullet["bullet"], NoOfWordsForVOPerBullet, course_name, directory)

        Topicvoiceover_query= f"Generate voiceover for {topic_name} in 100 words"
        Topicvoiceover, message = execute_query(Topicvoiceover_query, course_name, directory)
        topic["topic_voiceover"] = Topicvoiceover.replace("\n","")

    return topics


def save_topics_to_json(response, course_name, directory):
    # Parse the response string into a list of topics
    learning_objectives_query = "Generate 5 Learning objectives for a course made with this book"
    learning_objectives, message = execute_query(learning_objectives_query, course_name, DIRECTORY)
    learning_objectives = re.split("\n", learning_objectives)[1:]
    
    # learning_objective = learning_objective.replace("\n", "")

    topics_list = re.split("\\n", response)[1:]
    # topics_list = topics_list.replace("\n", "")

    # Create the course data dictionary
    course_data = {
        "course_name": course_name,
        "learning_objectives": learning_objectives,  # Assuming you will fill this in later
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

# def save_topics_to_json_less_than_2(response, course_name, directory):
#     # Parse the response string into a list of topics
#     topics_list = re.split("\d+\.\s", response)
#     learning_objectives_query = "Generate 5 Learning objectives for a course made with this book"
#     learning_objectives, message = execute_query(learning_objectives_query, course_name, DIRECTORY)
#     learning_objective = re.split("\d+\.\s", learning_objectives)[1:]
#     # Create the course data dictionary
#     course_data = {
#         "course_name": course_name,
#         "learning_objectives": learning_objective,  # Assuming you will fill this in later
#         "topics": [{"topic_name": topic} for topic in topics_list]
#     }

#     # Determine the path to the course directory
#     file_directory = os.path.join(directory, course_name)

#     # Determine the path to the course_data.json file
#     json_filepath = os.path.join(file_directory, 'course_data.json')

#     # Save the course data dictionary to the course_data.json file
#     with open(json_filepath, 'w') as f:
#         json.dump(course_data, f)
#     return course_data


def create_index(directory):
    documents = SimpleDirectoryReader(directory).load_data()
    llm_predictor = LLMPredictor(llm=OpenAI(temperature=0.15, model_name="text-curie-001", max_tokens=1800))
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
    index = GPTVectorStoreIndex.from_documents(documents, service_context=service_context)
    return index

def create_new_index(file_directory):
    file_index = create_index(file_directory)
    return file_index


def query_index(index, query):
    query_engine = index.as_query_engine()
    response = query_engine.query(query)
    return response


def does_directory_exist(course_name, path="data"):
    return course_name in os.listdir(path)


@app.route("/")
def hello_world():
    return "Hello world! hi"

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



@app.route('/upload_file', methods=['POST'])
def upload_file():
    try:
        logging.info("Uploading file...")

        if 'file' not in request.files:
            return jsonify({"error": "Missing file."}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "File not attached."}), 400

        filename = file.filename
        course_name = request.form['course_name']

        if not course_name:
            return jsonify({"error": "Missing Course_name."}), 400

        if does_directory_exist(course_name):
            return jsonify({"error": "Course already exists."}), 400
    
        course_settings = request.form.get('course_settings', None)

        if course_settings is None:
            return jsonify({"error": "Missing course settings."}), 400

        # Convert course_settings from JSON format to Python dictionary
        course_settings_dict = json.loads(course_settings)

        file_directory = os.path.join(DIRECTORY, course_name)
        filepath = os.path.join(file_directory, f"{filename}.pdf")
        os.makedirs(file_directory, exist_ok=True)
        file.save(filepath)

        # Save course_settings in a JSON file
        with open(os.path.join(file_directory, 'course_settings.json'), 'w') as f:
            json.dump(course_settings_dict, f)

        logging.info("Creating and saving index...")
        file_index = create_new_index(file_directory)

        file_index.storage_context.persist(file_directory)


        ###### Generate Topic  #####


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

        if NoOfTopics ==1:
            query = f"Generate a topic from the documents for a Course made From this Book"  
        else:
            query = f"Generate {str(NoOfTopics)} topics from the documents for a Course made From this Book"  
        
        directory=DIRECTORY

        # Ensure DIRECTORY is defined, or replace DIRECTORY with your desired default directory
        response, message = execute_query(query, course_name, directory)

        # if not response:
        #     return jsonify("message"), 400

        # if NoOfTopics<2:
        #     cdata = save_topics_to_json_less_than_2(response, course_name, directory)
        # else:
        cdata = save_topics_to_json(response, course_name, directory)
        
        # return jsonify(cdata)
        return jsonify({
            "statusCode": 200,
            "message": "Topics Saved successfully.",
            "isError": False,
            # "result": json.loads(str(cdata).replace("'", "\""))
            "result": cdata
        }), 200


        # return jsonify(f"Index created for {course_name}")
    
    except Exception as e:
        logging.exception("Error in /upload_file route")
        return jsonify({
            "statusCode": 500,  # Or appropriate error code
            "message": "An error occurred.",
            "isError": True,
            "result": {"error": str(e)}
        }), 500
    




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
        NoOfWordsForOverview = course_settings.get('NoOfWordsForOverview', None)
        NoOfWordsForVOOverview = course_settings.get('NoOfWordsForVOOverview', None)

        if NoOfSubTopicsPerTopic is None:
            return jsonify({"error": "NoOfSubTopicsPerTopic not found in course settings."}), 400
        
        # Construct the query strings
        directory=DIRECTORY
        subtopics = []
        all_topics = ""
        for topic in topics:
            topic_name = topic.get("topic_name", "").strip()
            all_topics = all_topics + " " + topic_name + ","
            if NoOfSubTopicsPerTopic ==1:
                query = f"Generate only 1 subtopic from the document for the topic '{topic_name}'"
            else:
                query = f"Generate {str(NoOfSubTopicsPerTopic)} subtopics from the document for the topic '{topic_name}'"

            # query = f"Generate {str(NoOfSubTopicsPerTopic)} subtopics from the document for the topic '{topic_name}'"
            response, message = execute_query(query, course_name, directory)
            response_subtopics = re.split("\n", response)[1:]
            
            # Transform each subtopic into a dictionary with a key `subtopic_name`
            response_subtopics = [{"subtopic_name": subtopic.replace("Subtopic ", "")} for subtopic in response_subtopics]

            # Add the list of subtopics to the current topic dictionary 
            topic['subtopics'] = response_subtopics

        # all_topics_String = all_topics.join(", ")

        Overview_query = f"Generate a combine script in {NoOfWordsForOverview} words with the following words '{all_topics}'"
        Overview, message = execute_query(Overview_query, course_name, directory)
        
        Overview_VO_query = f"Generate a combine voiceover script in {NoOfWordsForVOOverview} words with the following words '{all_topics}'"
        Overview_Voiceover, message = execute_query(Overview_VO_query, course_name, directory)


        # Save the updated topics list with subtopics to course_data.json
        course_data_filepath = os.path.join(file_directory, 'course_data.json')
        with open(course_data_filepath, 'r') as f:
            course_data = json.load(f)
        
        course_data["Overview_"] = Overview.replace("\n","")
        course_data["Overview_Voiceover"] = Overview_Voiceover.replace("\n","")

        course_data['topics'] = topics
        with open(course_data_filepath, 'w') as f:
            json.dump(course_data, f)

        # return jsonify(course_data)
        return jsonify({
            "statusCode": 200,
            "message": "Topics Saved successfully.",
            "isError": False,
            "result": course_data
        }), 200

    except Exception as e:
        logging.exception("Error in /saveTopics route")
        # return jsonify({"error": str(e)}), 500
        return jsonify({
            "statusCode": 500,  # Or appropriate error code
            "message": "An error occurred.",
            "isError": True,
            "result": {"error": str(e)}
        }), 500



@app.route('/saveSubtopics', methods=['POST'])
def saveSubtopics():
    try:
        data = request.get_json()
        course_name = data.get("course_name")
        topics = data.get("topics")
        # topic_summary = data.get("topic_summary")
        
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

        newTopics = saveSubTopicBullets(topics, course_settings, course_name, directory)


        course_data["topics"] = newTopics

        

        with open(course_data_filepath, 'w') as f:
            json.dump(course_data, f, indent=4)
      
        # return jsonify(course_data)
        return jsonify({
            "statusCode": 200,
            "message": f"Subtopics Saved successfully. ",
            "isError": False,
            # "result": json.loads(str(course_data).replace("'", "\""))
            "result": course_data
        }), 200

    except Exception as e:
        logging.exception("Error in /saveSubtopics route")
        # return jsonify({"error": str(e)}), 500
        return jsonify({
            "statusCode": 500,  # Or appropriate error code
            "message": "An error occurred.",
            "isError": True,
            "result": {"error": str(e)}
        }), 500





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

        topics = saveSubTopicBulletsWithVO(topics, course_settings, course_name, directory)
        # return topics
        # for new_topic in topics:
        #     for old_topic in course_data["topics"]:
        #         if new_topic["topic_name"] == old_topic["topic_name"]:
        #             old_topic["subtopics"] = new_topic["subtopics"]

        course_data["topics"] = topics


        # Save updated course data back to the course_data.json file
        with open(course_data_filepath, 'w') as f:
            json.dump(course_data, f, indent=4)

       
        # return jsonify({"message": course_data}), 200
        return jsonify({
            "statusCode": 200,
            "message": "Topics, subtopics and Voiceovers Saved successfully.",
            "isError": False,
            "result": course_data
        }), 200

    except Exception as e:
        logging.exception("Error in /saveTopicSummary route")
        # return jsonify({"error": str(e)}), 500
        return jsonify({
            "statusCode": 500,  # Or appropriate error code
            "message": "An error occurred.",
            "isError": True,
            "result": {"error": str(e)}
        }), 500



if __name__ == '__main__':
    app.run(debug=True)
