FROM mcr.microsoft.com/dotnet/core/aspnet:3.1 AS base
WORKDIR /app
EXPOSE 80

# Install NLog
RUN dotnet add package NLog

# Copy the default files
COPY . .

# Build the application
RUN dotnet build

# Run the application
CMD ["dotnet", "run"]
