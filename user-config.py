# This is a sample file. You can use generate_user_files script
# to create your user-config.py file:
# pwb generate_user_files

mylang = 'en'
family = 'fosswiki'
usernames['fosswiki']['en'] = 'Hamachitan'
# https://www.mediawiki.org/wiki/Manual:Pywikibot/User-agent
user_agent_format = 'Hamachitan ({script_comments})'
user_agent_description = open('./hamachitan_user_agent.txt').read().strip()
