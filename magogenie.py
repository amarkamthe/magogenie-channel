import time
import sys
import json
from ricecooker.classes.nodes import Channel, Video, Audio, Document, Topic, Exercise, guess_content_kind
from ricecooker.classes.questions import PerseusQuestion, MultipleSelectQuestion, SingleSelectQuestion, FreeResponseQuestion, InputQuestion
from ricecooker.exceptions import UnknownContentKindError, UnknownQuestionTypeError, raise_for_invalid_channel
from le_utils.constants import content_kinds, file_formats, format_presets, licenses, exercises
from urllib.request import urlopen,HTTPError
from multiprocessing import Pool
from settings import *
import re

ANSWER_TYPE = [
        'radio',
        'multiple_select'
    ]

ANSWER_TYPE_KEY = {
    'radio': ('correct_answer', exercises.SINGLE_SELECTION, 'all_answers' ),
    'multiple_select': ('correct_answers',exercises.MULTIPLE_SELECTION, 'all_answers' ),
    'number':('answers',exercises.INPUT_QUESTION ),
    'text': ('answers',exercises.INPUT_QUESTION ),
    'subjective':('answers',exercises.FREE_RESPONSE)
}

regex = re.compile('data:image\/jpeg;base64,(?:[A-Za-z0-9+\/]{4})*(?:[A-Za-z0-9+\/]{2}==|[A-Za-z0-9+\/]{3}=)*')

def question_list(question_ids):
    levels = {}
    question_url = QUESTION_URL%(','.join(map(str,question_ids)))
    # conn = urllib2.urlopen(question_url)
    # question_data = json.loads(conn.read())
    conn = urlopen(question_url)
    question_info = json.loads(conn.read().decode('utf8'))
    conn.close()
    levels = {}
    for key4, value4 in question_info.items():
        question_data = {}
        if question_info[str(key4)]['success']:
            if str(value4['question']['answer_type']) in ANSWER_TYPE_KEY:
                question_data['id'] = str(value4['question']['id'])
                question_data['question'] = value4['question']['content']#re.sub(regex, lambda m: "![]({})".format(m.group(0)), value4['question']['content'])
                question_data['type'] = ANSWER_TYPE_KEY[value4['question']['answer_type']][1]
                possible_answers = []
                correct_answer = []
                for answer in value4['possible_answers']:
                    possible_answers.append(answer['content'])
                    if answer['is_correct']:
                        correct_answer.append(answer['content'])

                if str(value4['question']['answer_type']) == str(ANSWER_TYPE[0]):
                    correct_answer = correct_answer[0]

                if str(value4['question']['answer_type']) == str(ANSWER_TYPE[0]) or str(value4['question']['answer_type']) == str(ANSWER_TYPE[1]):
                    question_data[(ANSWER_TYPE_KEY[(value4['question']['answer_type'])][2])] = possible_answers
                question_data[(ANSWER_TYPE_KEY[(value4['question']['answer_type'])][0])] = correct_answer
                level_val = value4['question']['difficulty_level']
                if level_val not in levels:
                    val = 'level' + str(level_val)
                    levels[level_val] = { 'id': val, 'title':val, 'questions':[], 'mastery_model' : exercises.M_OF_N ,'license' : licenses.CC_BY_NC_SA }


                levels[level_val]['questions'].append(question_data)
        else:
            continue
            
    return levels

def get_magogenie_info_url():
    SAMPLE = []
    #data =json.loads(urllib2.urlopen(url).read())
    response = urlopen(TREE_URL).read().decode('utf8')
    data = json.loads(response)
    print ("Topic received")    

    for key, value in data['boards'].items():
      if key =="BalBharati":
       board = dict()
       board['id'] = key
       board['title'] = key
       board['description'] = key
       board['children'] = []
       for key1, value1 in value['standards'].items():

        if key1 == "8":
            print (key+" Standards - " + key1)
            standards = dict()
            standards['id'] = key1
            standards['title'] = key1
            standards['description'] = key1
            standards['children'] = []

            for key2, value2 in value1['subjects'].items():
                subjects = dict()
                subjects['id'] = key2
                subjects['title'] = key2
                subjects['description'] = key2
                subjects['children']=[]

                topics = []
                for key3, value3 in value2['topics'].items():
                    topic_data = dict()
                    topic_data["ancestry"] = None
                    if value3['ancestry']:
                        topic_data["ancestry"]  = str(value3['ancestry'])
                    topic_data["id"] = str(value3['id'])
                    topic_data["title"] = value3['name']
                    topic_data["license"] = licenses.CC_BY_NC_SA
                    topic_data["mastery_model"] = exercises.M_OF_N
                    topic_data["children"] = []
                    if value3['question_ids']:

                        f = lambda A, n=6: [A[i:i+n] for i in range(0, len(A), n)]
                        levels = {}
                        p = Pool(5)
                        arrlevels = p.map(question_list, f(value3['question_ids'])[:3])#, chunksize=6)
                        p.close()
                        p.join()

                        for arrlevel in arrlevels:
                            for key0,val0 in arrlevel.items():
                                if key0 not in levels:
                                    levels[key0] = val0
                                else:
                                    levels[key0]['questions'].extend(val0['questions'])
                        
                        for index, level in levels.items():
                            topic_data["children"].append(level)
                        
                    topics.append(topic_data)
                result = build_magogenie_tree(topics)
                print (key + '--' + key1 + '--' + key2 )
                standards['children'] = result	
                
            board['children'].append(standards)
        
       SAMPLE.append(board)	  
    #print("Done ...")
    return SAMPLE

# Bulid magogenie_tree 
def build_magogenie_tree(topics): 
    topic_dict = dict((str(topic['id']), topic) for topic in topics)
                
    for topic in topics:
        if topic['ancestry'] != None and str(topic['ancestry']) in topic_dict:
            parent = topic_dict[str(topic['ancestry'])]
            question_parent = topic_dict[str(topic['id'])]
            parent.setdefault('children', []).append(topic)

    result = [topic for topic in topics if topic['ancestry'] == None]

    return result

# Constructing Magogenie Channel
def construct_channel(result=None):

    result_data = get_magogenie_info_url()

    channel = Channel(
        domain="learningequality.org",
        channel_id="Magogenie-channel_v1",
        title="Magogenie channel",
    )

    _build_tree(channel, result_data)
    raise_for_invalid_channel(channel)
    return channel

# Build tree for channel
def _build_tree(node, sourcetree):
    for child_source_node in sourcetree:
        try:
            kind = guess_content_kind(child_source_node.get("file"), child_source_node.get("questions"))
        except UnknownContentKindError:
            continue

        if kind == content_kinds.TOPIC:
            child_node = Topic(
                id=child_source_node["id"],
                title=child_source_node["title"],
                author=child_source_node.get("author"),
                description=child_source_node.get("description"),
            )
            node.add_child(child_node)

            source_tree_children = child_source_node.get("children", [])

            _build_tree(child_node, source_tree_children)

        elif kind == content_kinds.EXERCISE:
            child_node = Exercise(
                id=child_source_node["id"],
                title=child_source_node["title"],
                author=child_source_node.get("author"),
                description=child_source_node.get("description"),
                files=child_source_node.get("file"),
                exercise_data={'mastery_model': child_source_node.get("mastery_model"), 'randomize': True, 'm': 3, 'n': 5},
                license=child_source_node.get("license"),
                thumbnail=child_source_node.get("thumbnail"),
            )
            for q in child_source_node.get("questions"):
                question = create_question(q)
                child_node.add_question(question)
            node.add_child(child_node)

        else:                   # unknown content file format
            continue
    return node

def create_question(raw_question):

    if raw_question["type"] == exercises.MULTIPLE_SELECTION:
        return MultipleSelectQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            correct_answers=raw_question["correct_answers"],
            all_answers=raw_question["all_answers"],
            hints=raw_question.get("hints"),
        )
    if raw_question["type"] == exercises.SINGLE_SELECTION:
        return SingleSelectQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            correct_answer=raw_question["correct_answer"],
            all_answers=raw_question["all_answers"],
            hints=raw_question.get("hints"),
        )
    if raw_question["type"] == exercises.INPUT_QUESTION:
        return InputQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            answers=raw_question["answers"],
            hints=raw_question.get("hints"),
        )
    if raw_question["type"] == exercises.FREE_RESPONSE:
        return FreeResponseQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            hints=raw_question.get("hints"),
        )
    if raw_question["type"] == exercises.PERSEUS_QUESTION:
        return PerseusQuestion(
            id=raw_question["id"],
            raw_data=raw_question["item_data"],
        )
    else:
        raise UnknownQuestionTypeError("Unrecognized question type '{0}': accepted types are {1}".format(raw_question["type"], [key for key, value in exercises.question_choices]))
