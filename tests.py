#############################################################################
#       pytest -x <file_name>            # stop after first failure         #
#       pytest --maxfail=2 <file_name>   # stop after two failures          #
#       pytest <file_name>               # run all the test cases           #
#                                                                           #  
#                                                                           #
#############################################################################


import pytest 
import requests
from urllib.request import urlopen,HTTPError
import json
from settings import *

question_type = ["radio","multiple_select","number","text","subjective"]
level = [1,2,3]
@pytest.fixture
def check_tree_url():
    '''
    This method returns the status code of magogenie tree URL
    '''
    try:
        print (TREE_URL)
        res = requests.head(TREE_URL)
        return(res.status_code)
    except Exception as e:
        print("Error::"+str(e))

@pytest.fixture
def get_ID():
    '''
    This method returns ID of question which is input
     '''
    return "89555"

@pytest.fixture
def check_question_url(get_ID):
    '''
    This method returns the status code of question URL
    '''
    try:
        res = requests.head(QUESTION_URL%get_ID)
        return(res.status_code)
    except Exception as e:
        print("Error::"+str(e))

@pytest.fixture
def id_present_in_magogenie(check_question_url,get_ID):
    '''
    This method returns the success of question ID otherwise returns False
    '''
    if check_question_url == 200:
        conn = urlopen(QUESTION_URL%get_ID)
        question_data = json.loads(conn.read().decode('utf8'))
        if question_data[get_ID]["success"] == True:
            return True
        else:
            return False
    else:
        return False

@pytest.fixture
def detect_given_id_level(check_question_url,get_ID):
    '''
    This method returns difficulty level of question otherwise retuns -1
    '''
    if check_question_url == 200:
        conn = urlopen(QUESTION_URL%get_ID)
        question_data = json.loads(conn.read().decode('utf8'))
        if question_data[get_ID]["success"] == True:
            return(question_data[get_ID]["question"]["difficulty_level"])
        else:
            print("Question ID data not found")
            return(False)
    else:
        return -1

@pytest.fixture
def question_type_of_id(get_ID,check_question_url):
    '''
    This method retuns answer type of question otherwise returns None
    '''
    if check_question_url == 200:
        conn = urlopen(QUESTION_URL%get_ID)
        question_data = json.loads(conn.read().decode('utf8'))
        if question_data[get_ID]["success"] == True:
            return(question_data[get_ID]["question"]["answer_type"])
        else:
            print("Question ID data not found")
            return(False)
    else :
        return None


class TestUserHandling:
    '''
    All the test cases are written under the class.
    '''
    def test_url_of_tree(self,check_tree_url):
        '''
        Test is written to test whether magogenie tree URL is working or not 
        '''
        print("Magogenie Main URL Status ::" + str(check_tree_url))
        assert 200 == check_tree_url

    def test_url_of_question(self,check_question_url):
        '''
        Test is written to test whether magogenie question URL is working or not
        '''
        print("Question URL Status ::" + str(check_question_url))
        assert 200 == check_question_url

    def test_id_present_in_magogenie(self,id_present_in_magogenie):
        '''
        Test is written to test whether ID of question is valid or not
        '''
        assert True == id_present_in_magogenie

    def test_detect_given_id_level(self,detect_given_id_level):
        '''
        Test is written to test whether level of question is valid or not
        '''
        assert 3 in level

    def test_question_type_of_id(self,question_type_of_id):
        '''
        Test is written to test whether answer type is present in list
        '''
        assert True == bool(question_type_of_id in question_type)

