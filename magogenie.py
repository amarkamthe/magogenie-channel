
import time
import sys
import json
import os
from enum import Enum
from ricecooker.classes import nodes, questions, files
from ricecooker.classes.licenses import get_license
from ricecooker.exceptions import UnknownContentKindError, UnknownFileTypeError, UnknownQuestionTypeError, raise_for_invalid_channel
from le_utils.constants import content_kinds,file_formats, format_presets, licenses, exercises, languages
from pressurecooker.encodings import get_base64_encoding
from urllib.request import urlopen, HTTPError
from multiprocessing import Pool
from settings import *
import re
import itertools
import pickle
from time import gmtime, strftime
import operator
from bs4 import BeautifulSoup
import html2text
import subprocess
import time
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
class FileTypes(Enum):
    """ Enum containing all file types Ricecooker can have

        Steps:
            AUDIO_FILE: mp3 files
            THUMBNAIL: png, jpg, or jpeg files
            DOCUMENT_FILE: pdf files
    """
    AUDIO_FILE = 0
    THUMBNAIL = 1
    DOCUMENT_FILE = 2
    VIDEO_FILE = 3
    YOUTUBE_VIDEO_FILE = 4
    VECTORIZED_VIDEO_FILE = 5
    VIDEO_THUMBNAIL = 6
    YOUTUBE_VIDEO_THUMBNAIL_FILE = 7
    HTML_ZIP_FILE = 8
    SUBTITLE_FILE = 9
    TILED_THUMBNAIL_FILE = 10
    UNIVERSAL_SUBS_SUBTITLE_FILE = 11
    BASE64_FILE = 12
    WEB_VIDEO_FILE = 13


FILE_TYPE_MAPPING = {
    content_kinds.AUDIO : {
        file_formats.MP3 : FileTypes.AUDIO_FILE,
        file_formats.PNG : FileTypes.THUMBNAIL,
        file_formats.JPG : FileTypes.THUMBNAIL,
        file_formats.JPEG : FileTypes.THUMBNAIL,
    },
    content_kinds.DOCUMENT : {
        file_formats.PDF : FileTypes.DOCUMENT_FILE,
        file_formats.PNG : FileTypes.THUMBNAIL,
        file_formats.JPG : FileTypes.THUMBNAIL,
        file_formats.JPEG : FileTypes.THUMBNAIL,
    },
    content_kinds.HTML5 : {
        file_formats.HTML5 : FileTypes.HTML_ZIP_FILE,
        file_formats.PNG : FileTypes.THUMBNAIL,
        file_formats.JPG : FileTypes.THUMBNAIL,
        file_formats.JPEG : FileTypes.THUMBNAIL,
    },
    content_kinds.VIDEO : {
        file_formats.MP4 : FileTypes.VIDEO_FILE,
        file_formats.VTT : FileTypes.SUBTITLE_FILE,
        file_formats.PNG : FileTypes.THUMBNAIL,
        file_formats.JPG : FileTypes.THUMBNAIL,
        file_formats.JPEG : FileTypes.THUMBNAIL,
    },
    content_kinds.EXERCISE : {
        file_formats.PNG : FileTypes.THUMBNAIL,
        file_formats.JPG : FileTypes.THUMBNAIL,
        file_formats.JPEG : FileTypes.THUMBNAIL,
    },
}



def guess_file_type(kind, filepath=None, youtube_id=None, web_url=None, encoding=None):
    """ guess_file_class: determines what file the content is
        Args:
            filepath (str): filepath of file to check
        Returns: string indicating file's class
    """
    if youtube_id:
        return FileTypes.YOUTUBE_VIDEO_FILE
    elif web_url:
        return FileTypes.WEB_VIDEO_FILE
    elif encoding:
        return FileTypes.BASE64_FILE
    else:
        ext = os.path.splitext(filepath)[1][1:].lower()
        if kind in FILE_TYPE_MAPPING and ext in FILE_TYPE_MAPPING[kind]:
            return FILE_TYPE_MAPPING[kind][ext]
    return None

def guess_content_kind(path=None, web_video_data=None, questions=None):
    """ guess_content_kind: determines what kind the content is
        Args:
            files (str or list): files associated with content
        Returns: string indicating node's kind
    """
    # If there are any questions, return exercise
    if questions and len(questions) > 0:
        return content_kinds.EXERCISE

    # See if any files match a content kind
    if path:
        ext = path.rsplit('/', 1)[-1].split(".")[-1].lower()
        if ext in content_kinds.MAPPING:
            return content_kinds.MAPPING[ext]
        raise InvalidFormatException("Invalid file type: Allowed formats are {0}".format([key for key, value in content_kinds.MAPPING.items()]))
    elif web_video_data:
        return content_kinds.VIDEO
    else:
        return content_kinds.TOPIC

ANSWER_TYPE = [
        'radio',
        'multiple_select'
    ]

DESCRIPTION = "v0.1"

# ANSWER_TYPE_KEY to define new types of questions
ANSWER_TYPE_KEY = {
    'radio': ('correct_answer', exercises.SINGLE_SELECTION, 'all_answers'),
    'multiple_select': ('correct_answers', exercises.MULTIPLE_SELECTION, 'all_answers'),
    'number': ('answers', exercises.INPUT_QUESTION),
    'text': ('answers')
    # 'subjective': ('answers', exercises.FREE_RESPONSE)
}
# List of question units 
arrlevels = []
mathml_question_list = []
regex_image = re.compile('(\/assets.+?.(jpeg|jpg|png|gif){1})|\/wirispluginengine([^\"]+)')
# regex_base64 = re.compile('data:image\/[A-Za-z]*;base64,(?:[A-Za-z0-9+\/]{4})*(?:[A-Za-z0-9+\/]{2}==|[A-Za-z0-9+\/]{3}=|[&#A-Za-z0-9;+\/])*')
regex_base64 = re.compile('data:image\/[A-Za-z]*;base64,(?:[A-Za-z0-9+\/]{4})*(?:[A-Za-z0-9+\/]{2}==|[A-Za-z0-9+\/]{3}=)*')
regex_bmp = re.compile('((image\/bmp))')
regex_gif = re.compile('((image\/gif))')
IMG_ALT_REGEX = r'\salt\s*=\"([^"]+)\"' # used to remove alt tag from questions
mathml_re = re.compile(r"""(<math xmlns="http://www.w3.org/1998/Math/MathML">.*?</math>)""") # used to detect mathml in question
regex = r"(^\$\s[A-Za-z]+)" # used ti identify the valid mathml or not

regex_parse_invalid_mathml_questions = r"([\\_.]+\$)"
#regex_parse_invalid_mathml_questions = r"([a-zA-Z(\s)]+.[\\_.]+.\$)"  # used to handle e.g $ 5 \times 6 equals \_\_\_\_\_$
# regex_find_non_mathml_string = re.compile('(\$[(a-zA-z0-9)(\s.,?=÷+)]+\$)')
regex_find_non_mathml_string = r"(\$.[a-zA-Z0-9\s+,.=?_\\-]+\$)" # used to handle e.g $ Add .236+451+103 $
regex_parse_phantom = r"(\\phantom{\\[a-zA-Z]+{[a-zA-Z0-9]+}{[a-zA-Z0-9]+}})" # used to remove unnecessry conversion of mathml
regex_parse_invalid_mathml = r"(^\$\s[A-Za-z\s:|.|?|,]+)" # used to hndle the nonmathl (replace starting '$' before any word and replace it before mathml equation)

regex1 = r"(}[a-zA-Z0-9=+,\s.\\_  ?]+\$)"
#regex2 = r"(\$.[a-zA-Z0-9+=,?:. ÷_]+.(\\o|\\t|\\f))"
regex2 = re.compile('(\$.[a-zA-Z0-9+=,?:. ÷_ ]+.(\\o|\\t|\\f))')
# regex3 = r"(\}.[a-zA-Z0-9+=,?:. ]+.(\\m|\\t|\\f))"
regex3 = re.compile('(\}.[a-zA-Z0-9+=_,?:.  ]+.(\\m|\\t|\\f))')

regex4 =r"[0-9]\s[\\_.]+\$|[_]+\s\S"

regex5 = r"\$.*?\$"

convert_invalid_mathml_html2_text = [99842, 99843, 99844, 99845, 99846, 99849, 47036, 47037, 47038, 47039, 47053, 47052, 47054, 119868, 119865, 119866, 119867, 120078, 102483, 123708, 123709, 47040, 47055, 47056 ,138226,138225,138230,\
                    138229,138228,138227, 128232, 138231, 138233, 128164, 126147, 126172, 128146, 105158, 105141, 105180, 105166, \
                    118336, 118337, 118338, 138496, 138232, 138534, 138540, 138496, 138493, 138494, 138495, 123866, 106501,\
                    124250, 124249,124251, 124246, 124231, 124244, 124247, 124229, 124248, 124228, 124245, 124230, 124633,\
                    124636, 124631, 124627, 124629, 102914, 102997, 103108, 102994, 103019, 104668, 103550, 103602, 103618, \
                    142199, 103022,124913, 103289, 103291, 106911, 103501, 105177, 105043, 105162, 105181, 105215, 105041, 105210, 105045,\
                    105220, 105217, 98592, 98707, 98709, 98713, 98724, 98721, 105110, 98619, 105189, 105192, 98033, 115390, 109463, 109462,\
                    48091, 120951, 113202, 113175, 121109, 121105, 121101, 121964, 121130, 98776, 49959, 117515, 117514, 117527, 117524, 52823,\
                    117529, 49513, 13195, 48667, 122888, 122887, 118116, 131217, 131219, 131220, 131221, 131251, 50288, 50255, 50287, 50153,\
                    105184, 105185, 105186, 105190, 105255, 105257]
# This method takes question id and process it
def question_list(question_ids):
    levels = {}
    question_url = QUESTION_URL % (','.join(map(str, question_ids)))
    conn = urlopen(question_url)
    question_info = json.loads(conn.read().decode('utf-8'))
    conn.close()
    levels = [] 
    for key4, value4 in question_info.items():
        question_data = {}
        invalid_question_list = ['113178','119500','123348', '123350' , '123356', '123352', '123353','123351','123354','123355','123349','123357','126660', '45117', '112070','51216','136815','136816','136819']

        #and str(value4['question']['id']) not in invalid_question_list
        # this statement checks the success of question
        if question_info[str(key4)]['success'] and str(value4['question']['id']) not in invalid_question_list: # If question response is success then only it will execute following steps
            # This checks answer_type of question is defined in ANSWER_TYPE_KEY
            if (value4['question']['answer_type'] != "text"):
                if str(value4['question']['answer_type']) in ANSWER_TYPE_KEY:
                    question_data['id'] = str(value4['question']['id'])
                    question_data['question'] = re.sub(IMG_ALT_REGEX, lambda m: "".format(m.group(0)), value4['question']['content'])
                    question_data['question'] = question_data['question']+"\n Question ID:: "+question_data['id']
                    #print("Before png ::", question_data)
                    if int(question_data['id']) in convert_invalid_mathml_html2_text:
                        question_data['question'] = html2text.html2text(question_data['question'])
                        print ("question-0:",question_data['question']+"\n\n")

                    elif len(re.findall(mathml_re, question_data['question'])) > 0:
                        question_data['question'] = re.sub(mathml_re, lambda x : mathml_to_latex(x, question_data['id']), question_data['question'])
                        question_data['question'] = re.sub(regex_parse_phantom, lambda m:" ".format(m.group(0)), question_data['question'])
                        question_data['question'] = re.sub(r"\\overline{\)\s*}", lambda m:"\_\_\_\_\_\_".format(m.group(0)), question_data['question'])
                        question_data['question'] = question_data['question'].replace('\_','_')

                        res1 = re.search(regex1, question_data['question'])
                        print ("Main Question-1:",question_data['question'] + "\n\n")
                        success1 = None
                        if res1 is not None:
                            print ("First Result:",res1.group(0))
                            first_char = res1.group()[:1]
                            last_char = res1.group()[-1:]
                            original_question = res1.group()[1:]
                            match_data = first_char + last_char + original_question[:-1]
                            text_data = question_data['question'].split(str(res1.group()))
                            question_data['question'] = text_data[0] + match_data + text_data[1] 
                            # print ("question-1:", question_data['question']+"\n\n")
                            success1 = 1

                        res2 = re.search(r"(\$[a-zA-Z0-9+-=,?:. ÷_ ]+(\\m|\\o|\\t|\\f|\\s|\(|{|\\l))", question_data['question'])
                        # print ("RES2:", res2)
                        
                        print ("Main Question-2:", question_data['question'] + "\n\n")

                        success2 = None
                        if res2 is not None:
                            print ("Second Result:",res2.group(0))
                            valid_res = str(res2.group())[:-2].strip()
                            first_char = res2.group()[:1]
                            #print ("first_char:",first_char)
                            last_char = res2.group()[-2:]
                            #print ("last_char:",last_char)
                            original_question = res2.group()[1:]
                            match_data = original_question[:-2]
                            match_data= " ".join(match_data.split()) 
                            res2_1 = re.search(r"[0-9,=+ ]+$", match_data.strip())
                            #print ("match_data***:", match_data)

                            if res2_1 is not None:
                                #print("MATCHING RESULT:",res2_1.group(0))
                                valid_mathml_data_result = match_data.split(res2_1.group(0))
                                #print ("valid_mathml_data_result:***",valid_mathml_data_result)
                                match_data = valid_mathml_data_result[0] +" "+'  $' + res2_1.group(0) + valid_mathml_data_result[1]
                                #print ("valid_mathml_data_result:",match_data)
                            else:
                                match_data += " "+first_char
                                #print ("inside else match_data:", match_data)
                            match_data += " "+last_char
                            #print ("Outside else match_data:",match_data)
                            text_data = question_data['question'].split(str(res2.group()))
                            #print ("split data:",text_data)
                            if len(text_data) == 2:
                                question_data['question'] = text_data[0]+ " "+ match_data + text_data[1]
                            elif len(text_data) == 3:
                                question_data['question'] = text_data[0] + match_data + text_data[1] + match_data + text_data[2]
                            print ("question-2:",question_data['question']+"\n\n")
                            success2 = 1

                        res3 = re.search(r"(\}[a-zA-Z0-9=_,?:.  ]+(\\t|\\f|\\m|{))", question_data['question'])
                        print ("Main Question-3:",question_data['question'] + "\n\n")
                        success3 = None
                        if res3 is not None:
                            print ("Third Result:",res3.group(0))
                            first_char = res3.group()[:1]
                            last_char = res3.group()[-2:]
                            original_question = res3.group()[1:]
                            text_data = question_data['question'].split(str(res3.group()))
                            if len(text_data) <= 2:
                                match_data = first_char+" "+ '  $' + original_question[:-2]+ '  $' + last_char                        
                                question_data['question'] = text_data[0] + match_data + text_data[1] 
                                # print ("question-3:",question_data['question']+"\n\n")
                            success3 = 1

                        # question_data['question'] = re.sub(regex_parse_invalid_mathml, lambda m: (m.group(0) + ' $')[1:] .format(m.group(0)), question_data['question'])
                        # print ("question-1:",question_data['question']+"\n\n")
                        
                        # question_data['question'] = re.sub(regex_parse_invalid_mathml_questions, lambda m:(' $' + m.group(0))[:-1].format(m.group(0)),question_data['question'])
                        # print ("question-4:",question_data['question']+"\n\n")
                        print (str(success1)+""+ str(success2)+""+ str(success3))
                        if success1 == None and success2 == None and success3 == None and 'mathrm' not in question_data['question'] and '\\frac' not in question_data['question']: 
                            #question_data['question'] = re.sub(regex_find_non_mathml_string, lambda m:m.group(0).replace('$','').format(m.group(0)),question_data['question'])
                            question_data['question'] = question_data['question'].replace('$','')
                            question_data['question'] = question_data['question'].replace('\\times','$\\times$').replace('\\square','$\\square$')
                            print ("question-5:",question_data['question']+"\n\n")
                        else:
                            # print ("inside else statement")
                            res5 = re.search(r"\$.*?\$", question_data['question'])
                            # print ("Result- 5:",res5)
                            if res5 is not None:
                                matched_data = question_data['question'].split(res5.group())
                                # print ("matched_data****:",matched_data)
                                if matched_data:
                                    matched_data[0] = matched_data[0].replace('\\times','$\\times$').replace('\\square','$\\square$')
                                    #matched_data[1] = matched_data[1].replace('\\times','$\\times$').replace('\\square','$\\square$')
                                    question_data['question'] = matched_data[0]  + res5.group() +  matched_data[1] 
                        # print ("question-6:",question_data['question']+"\n\n")
                        question_data['question'] = html2text.html2text(question_data['question'])
                        question_data['question'] = re.sub(r"___", lambda m: ("\_\_\_") .format(m.group(0)), question_data['question'])
                        question_data['question'] = question_data['question'].replace('\\___$','\\_$').replace('\overline{ }','\_\_\_\_\_\_')
                        # print ("question-7:",question_data['question']+"\n\n")
                        question_data['question'] = question_data['question'].replace('\\__','\\_')
                        question_data['question'] = " ".join(question_data['question'].split())
                        question_data['question'] = question_data['question'].replace("$ \\frac"," $ \\frac")
                        print ("question-8:", question_data['question'])
                        if '\\mathrm' in str(question_data['question']) and '\\times' in str(question_data['question']):
                           
                            with open("invalid_mathml_wiith_functions.txt","a") as f1:
                                f1.write(question_data['id']+ ",")
                        elif '\\mathrm' in str(question_data['question']) and '\\frac' in str(question_data['question']):
                            
                            with open("invalid_mathml_wiith_functions_1.txt","a") as f2:
                                f2.write(question_data['id']+ ",")
                        elif '\\mathbf' in str(question_data['question']) and '\\times' in str(question_data['question']):
                            with open("invalid_mathml_wiith_texts_.txt","a") as f3:
                                f3.write(question_data['id']+ ",")
                        elif '\\mathrm' in str(question_data['question']):
                            with open("invalid_mathml_wiith_only_texts.txt","a") as f3:
                                f3.write(question_data['id']+ ",")

                    else:
                        question_data['question'] = question_data['question'].replace('\n','').replace('\r','')
                        question_data['question'] = question_data['question'].replace('http://www.magogenie.com','').replace('../..','').replace("..",'')
                        question_data['question'] = re.sub(regex_image, lambda m: url+"{}".format(m.group(0)) if url not in m.group(0) else "{}".format(m.group(0)), question_data['question'])
                        question_data['question'] = html2text.html2text(question_data['question'].replace("\/", "/").replace('&#10;', ''))
                        question_data['question'] = re.sub(r"___", lambda m: ("\_\_\_") .format(m.group(0)), question_data['question'])
                        print("Question text:", question_data['question'])
                    question_data['question'] = re.sub(regex_gif, lambda m: "image/png".format(m.group(0)), question_data['question']) 
                    question_data['question'] = re.sub(regex_bmp, lambda m: "image/png".format(m.group(0)), question_data['question'])
                    question_data['type'] = ANSWER_TYPE_KEY[value4['question']['answer_type']][1]

                    if len(str(value4['question']['unit'])) > 0 and value4['question']['unit'] is not None:
                        question_data['question'] = question_data['question'] + "\n\n \_\_\_\_\_\_ " + str(value4['question']['unit'])
        
                    possible_answers = []
                    correct_answer = []
                    for answer in value4['possible_answers']:
                        v  = re.sub(IMG_ALT_REGEX, lambda m: "".format(m.group(0)), answer['content'])
                        v  = v.replace("http://www.magogenie.com", "").replace('../..','').replace("..",'')
                        if len(re.findall(mathml_re, v)) > 0:
                            v  = re.sub(mathml_re, lambda x : mathml_to_latex(x, str(answer['id'])), v)
                            print ("MathML:",v+"\n\n")
                        v = re.sub(regex_parse_invalid_mathml, lambda m: (m.group(0) + ' $')[1:] .format(m.group(0)), v)
                        # print ("After the Mathml:",v)
                        # v= v.replace('\overline{) }','')
                        v = re.sub(r"\\overline{\)\s}", lambda m:"".format(m.group(0)), v)
                        v = re.sub(regex_image, lambda m: url+"{}".format(m.group(0)) if url not in m.group(0) else "{}".format(m.group(0)), v)
                        v = html2text.html2text(v.replace("\n","").replace('&#10;',''))
                        v = v.strip()
                        print ("After html2text:",v)
                        v = re.sub(regex_bmp, lambda m: "image/png".format(m.group(0)), v) # converted bmp images to the png format as per ricecooker validation
                        v = re.sub(regex_gif, lambda m: "image/png".format(m.group(0)), v) # converted gif images to supported format of ricecooker
                        possible_answers.append(v)
                        if answer['is_correct']:
                            correct_answer.append(v)
                    # print ("possible_answers:",possible_answers)
                    if str(value4['question']['answer_type']) == str(ANSWER_TYPE[0]):
                        correct_answer = correct_answer[0]
                        question_data['hints'] = correct_answer[0]

                    if str(value4['question']['answer_type']) == str(ANSWER_TYPE[0]) or str(value4['question']['answer_type']) == str(ANSWER_TYPE[1]):
                        question_data[(ANSWER_TYPE_KEY[(value4['question']['answer_type'])][2])] = possible_answers
                    question_data[(ANSWER_TYPE_KEY[(value4['question']['answer_type'])][0])] = correct_answer
                    question_data['hints'] = correct_answer
                    question_data["difficulty_level"] = value4['question']['difficulty_level']
                    levels.append(question_data)
        else:
            continue
    return levels

def get_magogenie_info_url():
    SAMPLE = []
    data = {}
    try:
        conn = urlopen(TREE_URL,timeout=30)
        data = json.loads(conn.read().decode('utf-8'))
        conn.close()
    except Exception as e:
        print(e)
    
    print ("Topic received")
    # To get boards in descending order used[::-1]
    # We have tesing here only for BalBharati board 
    for key in ['BalBharati']:#sorted(data['boards'].keys())[::-1]:     
        value = data['boards'][key]
        board = dict()
        board['id'] = key
        board['title'] = key
        board['description'] = DESCRIPTION
        board['children'] = []
        # To get standards in ascending order
        # we have use 6th std for testing purpose
        for key1 in ['8']:#sorted(value['standards'].keys()):  
            value1 = value['standards'][key1]
            print (key+" Standards - " + key1)
            standards = dict()
            standards['id'] = key1
            standards['title'] = key1
            standards['description'] = DESCRIPTION
            standards['children'] = []
            # To get subject under the standard
            for key2, value2 in value1['subjects'].items():
                subjects = dict()
                subjects['id'] = key2
                subjects['title'] = key2
                subjects['description'] = DESCRIPTION
                subjects['children'] = []

                topics = []
                # To get topic names under subjects
                for key3 in ['Squares and Square Roots','Positive and negative square roots']:#['Fractions', 'Converting unlike fractions into like fractions']: #value3 in value2['topics'].items():#['Operations on Rational Numbers','Addition and Subtraction of Rational Numbers, and Additive Inverses']: #value3 in value2['topics'].items():
                    value3 = value2['topics'][key3]
                    topic_data = dict()
                    topic_data["ancestry"] = None
                    if value3['ancestry']:
                        topic_data["ancestry"] = str(value3['ancestry'])
                    topic_data["id"] = str(value3['id'])
                    topic_data["title"] = value3['name']
                    topic_data["description"] = DESCRIPTION
                    topic_data["license"] = licenses.ALL_RIGHTS_RESERVED
                    topic_data["mastery_model"] = exercises.M_OF_N
                    topic_data["children"] = []
                    if value3['question_ids']:
                        # To take 6 question ids and put into URL for getting result
                        f = lambda A, n=6: [A[i:i+n] for i in range(0, len(A), n)]
                        levels = {}
                        p = Pool(5)
                      
                        try:
                            arrlevels = []
                            arrlevels = p.map(question_list, f(value3['question_ids']))
                            p.close()
                            p.join()
                        except Exception as e:
                            print (e)
                        
                        # To convert multiple list into single list
                        newlist = list(itertools.chain(*arrlevels))  
                        # To sort data levelwise 
                        arrlevels = sorted(newlist, key=lambda k: k["id"])  
                        newlist = []
                        level = {}

                        # This code seperates the different questions based on level
                        for i in arrlevels:
                            diff = i["difficulty_level"]
                            if i["difficulty_level"] not in levels:
                                if str(i["difficulty_level"]) == "3":
                                    val = "Challenge Set"
                                    source_id_unique = val + "_" + str(value3['id'])  # To handle the mismatch between same source id of different nodes   
                                else:
                                    val = 'Level ' + str(i["difficulty_level"])
                                    source_id_unique = val + "_" + str(value3['id'])  
                                levels[diff] = {'id': source_id_unique, 'title': val, 'questions': [], 'description':DESCRIPTION, 'mastery_model': exercises.M_OF_N, 'license': licenses.ALL_RIGHTS_RESERVED, 'domain_ns': 'GreyKite Technologies Pvt. Ltd.', 'Copyright Holder':'GreyKite Technologies Pvt. Ltd.'}
                            levels[diff]["questions"].append(i)
                        arrlevels = []
                        arrlevels.append(levels)

                        for index, level in levels.items():
                            topic_data["children"].append(level)
                    topics.append(topic_data)
                # calling build_magoegnie_tree by passing topics to create a magogenie tree 
                result = build_magogenie_tree(topics)  
            print(key + '--' + key1 + '--' + key2)
            standards['children'] = result
            print(time.asctime(time.localtime(time.time())))  
            # Printing time and date of standard upload
            board['children'].append(standards)
        SAMPLE.append(board)
    return SAMPLE

# Bulid magogenie_tree
def build_magogenie_tree(topics):
    # To sort topics data id wise 
    #tpo = sorted(topics, key=lambda k: k["id"])
    tpo = sorted(topics, key=operator.itemgetter("id"))
    topics = tpo
    count = 0
    for topic in topics:
        if topic['ancestry'] == None:
            count+= 1
            topic['title'] = str(str(count) + " " + topic['title'])
        else:
            for subtopic in topic['children']:
                subtopic['title'] =  subtopic['title'] + ": " + topic['title']

    topic_dict = dict((str(topic['id']), topic) for topic in topics)
    for topic in topics:
        if topic['ancestry'] != None and str(topic['ancestry']) in topic_dict:
            # for subtopic in topic['children']:
            #     subtopic['title'] =  subtopic['title'] + ": " + topic['title']
            parent = topic_dict[str(topic['ancestry'])]
            question_parent = topic_dict[str(topic['id'])]
            parent.setdefault('children', []).append(topic)
        # else:
        #     count+= 1
        #     topic['title'] = str(str(count) + " " + topic['title'])

    result = [topic for topic in topics if topic['ancestry'] == None]
    # print ("result:", json.dumps(result))
    # sys.exit(0)
    return result

# Constructing Magogenie Channelss
def construct_channel(result=None):

    result_data = get_magogenie_info_url()
    #print ("result_data:",json.dumps(result_data))
    channel = nodes.ChannelNode(
        source_domain="magogenie.com",
        source_id="Magogenie BalBharati Bug Fixes",
        title="Magogenie BalBharati Bug Fixes",
        thumbnail = "/Users/Admin/Documents/mago.png",
    )
    _build_tree(channel, result_data)
    raise_for_invalid_channel(channel)
    return channel

# Build tree for channel
def _build_tree(node, sourcetree):

    for child_source_node in sourcetree:
        try:
            main_file = child_source_node['files'][0] if 'files' in child_source_node else {}
            kind = guess_content_kind(path=main_file.get('path'), web_video_data=main_file.get('youtube_id') or main_file.get('web_url'), questions=child_source_node.get("questions"))
        except UnknownContentKindError:
            continue

        if kind == content_kinds.TOPIC:
            child_node = nodes.TopicNode(
                source_id=child_source_node["id"],
                title=child_source_node["title"],
                author=child_source_node.get("author"),
                description=child_source_node.get("description"),
                thumbnail=child_source_node.get("thumbnail"),
            )
            node.add_child(child_node)

            source_tree_children = child_source_node.get("children", [])

            _build_tree(child_node, source_tree_children)

        elif kind == content_kinds.EXERCISE:
            # node_data = json.dumps(child_source_node)
            if int(len(child_source_node['questions'])) < 5:
                exercise_data = {
                    'mastery_model': exercises.DO_ALL,
                    'randomize': True,
                }
            else:
                exercise_data={
                    'mastery_model': exercises.M_OF_N,
                    'randomize': True,
                    'm': 4,
                    'n': 5,
                }
            child_node = nodes.ExerciseNode(
                source_id=child_source_node["id"],
                title=child_source_node["title"],
                license=child_source_node.get("license"),
                author=child_source_node.get("author"),
                description=child_source_node.get("description"),
                exercise_data=exercise_data,
                copyright_holder='GreyKite Technologies Pvt. Ltd.',
                thumbnail=child_source_node.get("thumbnail"),
            )
    
            add_files(child_node, child_source_node.get("files") or [])
            for q in child_source_node.get("questions"):
                question = create_question(q)
                child_node.add_question(question)
            node.add_child(child_node)

        else:                   # unknown content file format
            continue

    return node

def add_files(node, file_list):
    for f in file_list:
        file_type = guess_file_type(node.kind, filepath=f.get('path'), youtube_id=f.get('youtube_id'), web_url=f.get('web_url'), encoding=f.get('encoding'))

        if file_type == FileTypes.AUDIO_FILE:
            node.add_file(files.AudioFile(path=f['path'], language=f.get('language')))
        elif file_type == FileTypes.THUMBNAIL:
            node.add_file(files.ThumbnailFile(path=f['path']))
        elif file_type == FileTypes.DOCUMENT_FILE:
            node.add_file(files.DocumentFile(path=f['path'], language=f.get('language')))
        elif file_type == FileTypes.HTML_ZIP_FILE:
            node.add_file(files.HTMLZipFile(path=f['path'], language=f.get('language')))
        elif file_type == FileTypes.VIDEO_FILE:
            node.add_file(files.VideoFile(path=f['path'], language=f.get('language'), ffmpeg_settings=f.get('ffmpeg_settings')))
        elif file_type == FileTypes.SUBTITLE_FILE:
            node.add_file(files.SubtitleFile(path=f['path'], language=f['language']))
        elif file_type == FileTypes.BASE64_FILE:
            node.add_file(files.Base64ImageFile(encoding=f['encoding']))
        elif file_type == FileTypes.WEB_VIDEO_FILE:
            node.add_file(files.WebVideoFile(web_url=f['web_url'], high_resolution=f.get('high_resolution')))
        elif file_type == FileTypes.YOUTUBE_VIDEO_FILE:
            node.add_file(files.YouTubeVideoFile(youtube_id=f['youtube_id'], high_resolution=f.get('high_resolution')))
        else:
            raise UnknownFileTypeError("Unrecognized file type '{0}'".format(f['path']))


def create_question(raw_question):

    if raw_question["type"] == exercises.MULTIPLE_SELECTION:
        return questions.MultipleSelectQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            correct_answers=raw_question["correct_answers"],
            all_answers=raw_question["all_answers"],
            hints=raw_question.get("hints"),
            randomize = True,
        )
    if raw_question["type"] == exercises.SINGLE_SELECTION:
        return questions.SingleSelectQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            correct_answer=raw_question["correct_answer"],
            all_answers=raw_question["all_answers"],
            hints=raw_question.get("hints"),
            randomize = True
        )
    if raw_question["type"] == exercises.INPUT_QUESTION:
        return questions.InputQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            answers=raw_question["answers"],
            hints=raw_question.get("hints"),
        )
    if raw_question["type"] == exercises.FREE_RESPONSE:
        return questions.FreeResponseQuestion(
            id=raw_question["id"],
            question=raw_question["question"],
            hints=raw_question.get("hints"),
        )
    if raw_question["type"] == exercises.PERSEUS_QUESTION:
        return questions.PerseusQuestion(
            id=raw_question["id"],
            raw_data=raw_question["item_data"],
            source_url="https://www.google.com/",
        )
    else:
        raise UnknownQuestionTypeError("Unrecognized question type '{0}': accepted types are {1}".format(raw_question["type"], [key for key, value in exercises.question_choices]))

def mathml_to_latex(match, q_id):
    match = match.group().replace("&gt;",">")
    match = match.replace('&nbsp;','')
    path = "/Users/Admin/Documents/magogenie-channel/q_files"
    #path = "/Users/Admin/Documents/MG/magogenie-channel/q_files"
    #print ("inside mathml_to_latex")
    filename = os.path.join(path, q_id+".mml")
    with open(filename,"w") as f:
        f.write(match)
    try:
        p = subprocess.Popen(["xsltproc", "mmltex.xsl", filename], stdout=subprocess.PIPE)
        output, err = p.communicate() 
        text = output.decode("utf-8")
        res = re.findall(regex, text)

        if len(res) != 0:
            with open('questions.txt',"a") as f:
                f.write( q_id+ ",")
 
        return output.decode("utf-8")
    except Exception as e:
        raise(e)

