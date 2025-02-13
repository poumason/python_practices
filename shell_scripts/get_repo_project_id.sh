# Set the token for authentication
token="glpat-6jzwm5Hxqs8QCQfV6UrP"

# Create a query parameter string containing the repository name and scope
query_params="scope=project&search=ci-template"

# Send the GET request to the /projects endpoint with the necessary headers and parameters, and pipe the response through jq
curl -X GET \
     --header "Authorization: Bearer $token" \
     https://gitlab.com/api/v4/projects?search=Pou/ci-template
