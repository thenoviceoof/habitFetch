import requests

class HabitApi(object):
    '''
    Fetch information HabitRPG.
    '''

    DIRECTION_UP = "up"
    DIRECTION_DOWN = "down"

    TYPE_HABIT = "habit"
    TYPE_DAILY = "daily"
    TYPE_TODO = "todo"
    TYPE_REWARD = "reward"

    def __init__(self, user_id, api_key, base_url = "https://habatica.com/"):
        self.user_id = user_id
        self.api_key = api_key
        self.base_url = base_url

    def auth_headers(self):
        return {
            'x-api-user': self.user_id,
            'x-api-key': self.api_key
        }

    def request(self, method, path, *args, **kwargs):
        '''Make a request to the API'''
        path = ("%s/%s" % ("api/v3", path)
                if not path.startswith("/") else
                path[1:])

        # Allow overriding headers, but default to using the given
        # authentication headers.
        if not "headers" in kwargs:
            kwargs["headers"] = self.auth_headers()

        # Call appropriate requests method using runtime hackery.
        return getattr(requests, method)(self.base_url + path, *args, **kwargs)

    def user(self):
        '''
        Get the authenticated user's profile.
        '''
        return self.request("get", "user").json()

    def tasks(self):
        '''
        Get the tasks associated with the current user.
        '''
        return self.request("get", "tasks/user").json()

    def completed_tasks(self):
        '''
        Get the completed tasks associated with the current user.
        '''
        parameters = {
            'type': 'completedTodos'
        }
        return self.request("get", "tasks/user", params=parameters).json()

    def task(self, task_id):
        '''
        Get the information for a specific task.
        '''
        return self.request("get", "tasks/%s" % task_id).json()
