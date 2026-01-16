FROM neo4j:5.26.7

ENV NEO4J_PLUGINS='["apoc", "apoc-extended"]'
ENV NEO4J_dbms_security_procedures_unrestricted=apoc.*
ENV NEO4J_apoc_export_file_enabled=true
ENV NEO4J_apoc_import_file_enabled=true

EXPOSE 7474 7687
