// Run these independently in the DOMAIN Browser at http://localhost:7476.
// Show domain nodes and relationships without taxonomy edges.
MATCH p=(a:GeoEntity)-[r]->(b:GeoEntity)
WHERE NOT a:Class AND NOT b:Class
RETURN p LIMIT 150;

// Taxonomy: classes, not actual wells.
MATCH p=(:Class)-[:SUBCLASS_OF]->(:Class) RETURN p;

// Evidence chain for W001, including source snapshot.
MATCH (w:Well {id:'well:W001'})<-[:ABOUT]-(o:Observation)
MATCH p=(o)-[:SOURCED_FROM]->(:SourceRecord)-[:PART_OF]->(:SourceDataset)
RETURN w,o,p;

// Quality issues, preserved source records, and associated observations.
MATCH p=(:QualityIssue)-[:FLAGS]->(r:SourceRecord)
OPTIONAL MATCH (o:Observation)-[:SOURCED_FROM]->(r)
RETURN p,o;

// A useful abstention: the source cannot establish reservoir temperature.
MATCH (o:Observation)-[:MEASURES]->(:ObservableProperty {id:'property:temperature'})
WHERE o.measurement_location='unknown'
RETURN o.title, 'Cannot claim reservoir temperature: location/depth unknown' AS limitation;
