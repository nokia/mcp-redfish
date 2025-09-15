# Retry Logic and Error Handling

The MCP Redfish server implements robust retry logic with exponential backoff to handle transient failures when communicating with Redfish APIs. This ensures reliable operation in environments with network instability, BMC load, or temporary service unavailability.

## Features

### Exponential Backoff
- **Progressive delays**: Each retry attempt waits longer than the previous one
- **Configurable factors**: Control how aggressively delays increase
- **Maximum delay cap**: Prevents excessively long waits
- **Jitter support**: Randomizes delays to avoid thundering herd problems

### Smart Retry Logic
- **Selective retrying**: Only retries transient errors (timeouts, rate limits, server errors)
- **Immediate failure**: Non-retryable errors (authentication, invalid requests) fail fast
- **Comprehensive logging**: Detailed visibility into retry attempts and failures

### Environment Configuration
All retry behavior can be configured via environment variables:

```bash
# Maximum number of retry attempts
REDFISH_MAX_RETRIES=3

# Initial delay between retries (seconds)
REDFISH_INITIAL_DELAY=1.0

# Maximum delay between retries (seconds)
REDFISH_MAX_DELAY=60.0

# Backoff multiplier for exponential growth
REDFISH_BACKOFF_FACTOR=2.0

# Enable jitter to avoid thundering herd (true/false)
REDFISH_JITTER=true
```

## Retryable Conditions

### HTTP Status Codes
The following HTTP status codes trigger retry attempts:
- **408** - Request Timeout
- **429** - Too Many Requests (Rate Limiting)
- **502** - Bad Gateway
- **503** - Service Unavailable
- **504** - Gateway Timeout

### Exception Types
These exception types are considered retryable:
- **ConnectionError** - Network connectivity issues
- **TimeoutError** - Request timeouts
- **OSError** - Operating system level errors
- **Generic Exception** - Redfish library exceptions

### Non-Retryable Conditions
These conditions cause immediate failure:
- **400** - Bad Request (client error)
- **401** - Unauthorized (authentication failure)
- **403** - Forbidden (authorization failure)
- **404** - Not Found (resource doesn't exist)
- **ValidationError** - Invalid configuration or parameters

## Operation Coverage

Retry logic is applied to all Redfish operations:

### Client Setup
- **Connection establishment**: Retries network connectivity issues
- **Authentication**: Retries temporary authentication service failures
- **Session creation**: Handles BMC load during session establishment

### Data Operations
- **GET requests**: Reliable resource data retrieval
- **POST requests**: Robust resource creation
- **PATCH requests**: Resilient resource updates
- **DELETE requests**: Dependable resource deletion

## Usage Examples

### MCP Client Usage
The retry logic is automatically applied to all MCP tool operations. When using an MCP client, all interactions benefit from robust retry handling:

```bash
# Start the MCP server with default retry configuration
uv run mcp-redfish

# In your MCP client (Claude Desktop, etc.), use tools normally:
# - "List all available servers" → uses list_endpoints with retry logic
# - "Get system information from server 192.168.1.100" → uses get_resource_data with retry logic
```

### Server Configuration
Configure retry behavior by setting environment variables before starting the MCP server:

```bash
# Configure for high-latency environment
export REDFISH_MAX_RETRIES=5
export REDFISH_INITIAL_DELAY=2.0
export REDFISH_MAX_DELAY=120.0
export REDFISH_BACKOFF_FACTOR=1.5

# Start the MCP server with custom retry settings
uv run mcp-redfish
```

### Development/Testing Configuration
Use faster retries for development and testing:

```bash
# Development environment - faster failures
export REDFISH_MAX_RETRIES=2
export REDFISH_INITIAL_DELAY=0.1
export REDFISH_JITTER=false  # Predictable timing for tests

# Start the server
uv run mcp-redfish
```

## Monitoring and Logging

### Observing Retry Behavior
Configure the MCP server with debug logging to see detailed retry information:

```bash
# Enable debug logging
export MCP_REDFISH_LOG_LEVEL=DEBUG

# Start the server
uv run mcp-redfish
```

When MCP tools encounter transient failures, you'll see logs like:

```
WARNING - Redfish GET request attempt 1 failed for /redfish/v1/Systems: Connection timeout. Retrying in 1.23 seconds...
WARNING - Redfish GET request attempt 2 failed for /redfish/v1/Systems: Connection timeout. Retrying in 2.45 seconds...
INFO - GET request for /redfish/v1/Systems succeeded on attempt 3
```

### MCP Tool Experience
From an MCP client perspective, retry logic provides seamless operation:

- **Transparent operation**: MCP tools like `get_resource_data` automatically handle transient failures
- **Consistent responses**: Tools return data successfully even when underlying network issues occur
- **Reasonable delays**: Built-in exponential backoff prevents overwhelming struggling infrastructure
- **Clear error messages**: Non-retryable errors (like authentication failures) are reported immediately

### Failure Analysis
When the MCP server encounters issues, retry failures include comprehensive context in the logs:
- Original exception details
- Number of attempts made
- Total time elapsed
- Configuration used

This information helps diagnose infrastructure issues and tune retry settings for your environment.

## Real-World Scenarios

### Scenario 1: BMC Under Load
```
Situation: Infrastructure BMC is processing firmware updates
MCP Behavior:
- First request gets 503 Service Unavailable
- Automatically retries with increasing delays
- Eventually succeeds when BMC load decreases
- AI agent receives requested data without intervention
```

### Scenario 2: Network Hiccup
```
Situation: Brief network connectivity issue
MCP Behavior:
- Connection timeout on initial request
- Retries with exponential backoff
- Succeeds on second attempt after 1-2 seconds
- Agent workflow continues seamlessly
```

### Scenario 3: Authentication Error
```
Situation: Invalid credentials provided
MCP Behavior:
- Receives 401 Unauthorized immediately
- Recognizes as non-retryable error
- Reports authentication failure to agent immediately
- No unnecessary retry attempts or delays
```

## Performance Considerations

### Resource Usage
- **Memory**: Minimal overhead for retry state tracking
- **CPU**: Negligible impact from delay calculations
- **Network**: Additional requests only for actual failures

### Timing Behavior
With default settings (3 retries, 2.0 backoff factor, 1.0s initial delay):
- **Attempt 1**: Immediate (0s)
- **Attempt 2**: ~1.0s delay (1.0 * 2.0^0)
- **Attempt 3**: ~2.0s delay (1.0 * 2.0^1)
- **Attempt 4**: ~4.0s delay (1.0 * 2.0^2)
- **Total worst case**: ~7 seconds

With jitter enabled, actual delays will vary randomly within reasonable bounds to prevent thundering herd problems.

### Advanced Configuration Examples

#### Custom Backoff Factor
```bash
# Aggressive backoff (delays grow quickly)
export REDFISH_BACKOFF_FACTOR=3.0
# Results: 1s, 3s, 9s delays

# Conservative backoff (delays grow slowly)
export REDFISH_BACKOFF_FACTOR=1.5
# Results: 1s, 1.5s, 2.25s delays
```

#### Jitter Configuration
```bash
# Disable jitter for predictable timing (testing/development)
export REDFISH_JITTER=false

# Enable jitter to prevent thundering herd (production)
export REDFISH_JITTER=true  # Default
```

### Tuning Guidelines

Choose retry configuration based on your infrastructure environment:

#### High-Reliability Environment
For critical infrastructure where availability is paramount:
```bash
export REDFISH_MAX_RETRIES=5
export REDFISH_INITIAL_DELAY=0.5
export REDFISH_BACKOFF_FACTOR=1.5  # Gentle backoff
export REDFISH_MAX_DELAY=60.0
export REDFISH_JITTER=true
```

#### Fast-Failure Environment
For development or environments where quick feedback is preferred:
```bash
export REDFISH_MAX_RETRIES=1
export REDFISH_INITIAL_DELAY=0.5
export REDFISH_BACKOFF_FACTOR=2.0
export REDFISH_MAX_DELAY=5.0
export REDFISH_JITTER=false  # Predictable for testing
```

#### Production Recommended
Balanced configuration for most production environments:
```bash
export REDFISH_MAX_RETRIES=3
export REDFISH_INITIAL_DELAY=1.0
export REDFISH_MAX_DELAY=30.0
export REDFISH_BACKOFF_FACTOR=2.0  # Standard exponential backoff
export REDFISH_JITTER=true         # Prevent thundering herd
```

## Integration with MCP Tools

The retry logic is transparently integrated with all MCP tools, providing a robust foundation for AI-driven infrastructure management:

### Available MCP Tools
- **`list_endpoints`**: Reliably lists configured Redfish endpoints with automatic retry on network issues
- **`get_resource_data`**: Robustly retrieves resource data (Systems, EthernetInterfaces, etc.) with retry handling
- **Future tools**: All new MCP tools automatically inherit retry behavior

### AI Agent Experience
When AI agents use the MCP server, retry logic ensures:

1. **Reliable operation**: Transient infrastructure issues don't break agent workflows
2. **Consistent responses**: Agents receive data successfully even during network hiccups
3. **Appropriate timeouts**: Failed operations timeout reasonably without hanging agent processes
4. **Clear error reporting**: Permanent failures (authentication, invalid resources) are reported immediately

### Example Agent Interaction
```
Agent: "Get the power state of system 1 from server 192.168.1.100"

MCP Server:
- Calls get_resource_data tool
- Encounters network timeout on first attempt
- Automatically retries with exponential backoff
- Successfully retrieves data on attempt 2
- Returns power state to agent seamlessly
```

This ensures that AI agents using the MCP server experience reliable, fault-tolerant infrastructure management capabilities without needing to implement their own retry logic.
