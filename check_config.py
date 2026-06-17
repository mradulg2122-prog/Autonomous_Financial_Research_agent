from backend.core.config import settings
print("base_url:", settings.openai_base_url)
print("model:", settings.openai_model)
print("embedding_model:", settings.openai_embedding_model)
print("key_prefix:", settings.openai_api_key[:15] + "...")
print("async_db_url:", settings.async_database_url.split("@")[-1])
print("redis_url:", settings.redis_connection_url.split("@")[-1])
print("qdrant_host:", settings.qdrant_host, "port:", settings.qdrant_port)
print("vector_size:", settings.qdrant_vector_size)
