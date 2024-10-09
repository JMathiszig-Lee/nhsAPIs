import base64
import logging
import pprint
import uuid
from datetime import datetime, timedelta

import xmltodict
from httpx import AsyncClient

from ..redis_connect import redis_client


def create_security():
    current_time = datetime.now()
    expiration_time = current_time + timedelta(minutes=5)

    current_timestamp = current_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    expiration_timestamp = expiration_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    security = {
        "@s:mustUnderstand": 1,
        "@xmlns:o": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
        "u:Timestamp": {
            "@u:Id": "_0",
            "u:Created": {"#text": current_timestamp},
            "u:Expires": {"#text": expiration_timestamp},
        },
    }

    return security


def create_header(message_urn: str, message_id: str):
    header = {
        "Action": {
            "@s:mustUnderstand": 1,
            "#text": message_urn,
        },
        "a:RelatesTo": {"#text": message_id},
        # "Security": create_security(),
    }
    return header


def create_envelope(header, body):
    envelope = {
        "s:Envelope": {
            "@xmlns:s": "http://www.w3.org/2003/05/soap-envelope",
            "@xmlns:a": "http://www.w3.org/2005/08/addressing",
            "@xmlns:u": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
            "s:Header": header,
            "s:Body": body,
        }
    }
    return envelope


async def iti_47_response(message_id, patient, query):

    gp = patient["generalPractitioner"][0]

    body = {
        "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
    }

    body["PRPA_IN201306UV02"] = {
        "@xmlns": "urn:hl7-org:v3",
        "@ITSVersion": "XML_1.0",
        "id": {"@root": str(uuid.uuid4())},
        "creationTime": {"@value": int(datetime.now().timestamp())},
        "interactionId": {
            "@root": "2.16.840.1.113883.1.18",
            "@extension": "PRPA_IN201306UV02",
        },
        "processingCode": {"@code": "T"},
        "processingModeCode": {"@code": "T"},
        "acceptAckCode": {"@code": "NE"},
        "receiver": {
            "@typeCode": "RCV",
            "device": {"@classCode": "DEV", "@determinerCode": "INSTANCE"},
        },
        "sender": {
            "@typeCode": "SND",
            "device": {"@classCode": "DEV", "@determinerCode": "INSTANCE"},
        },
        "acknowledgement": {
            "typeCode": {"@code": "AA"},
            "targetMessage": {"id": {"@root": message_id}},
        },
        "controlActProcess": {
            "@classCode": "CACT",
            "@moodCode": "EVN",
            "code": {
                "@code": "PRPA_TE201306UV02",
                "@codeSystem": "2.16.840.1.113883.1.18",
            },
            "authorOrPerformer": {
                "@typeCode": "AUT",
                "assignedDevice": {
                    "@classCode": "ASSIGNED",
                    "id": {"@root": "1.2.840.114350.1.13.1610.1.7.3.688884.100"},
                },
            },
            "subject": {
                "@typeCode": "SUBJ",
                "@contextConductionInd": "false",
                "registrationEvent": {
                    "@classCode": "REG",
                    "moodCode": "EVN",
                    "statusCode": {"@code": "active"},
                    "subject1": {
                        "@typeCode": "SBJ",
                        "patient": {
                            "@classCode": "PAT",
                            "id": {
                                "@root": "2.16.840.1.113883.2.1.4.1",
                                "@extension": patient["id"],
                            },
                            "statusCode": {"@code": "active"},
                            "patientPerson": {
                                "@classCode": "PSN",
                                "@determinerCode": "INSTANCE",
                                "name": {
                                    "given": {"#text": patient["name"][0]["given"][0]},
                                    "family": {"#text": patient["name"][0]["family"]},
                                },
                                "administrativeGenderCode": {
                                    "@code": patient["gender"]
                                },
                                "birthTime": {"@value": patient["birthDate"]},
                            },
                            "providerOrganization": {
                                "@classCode": "ORG",
                                "@determinerCode": "INSTANCE",
                                "id": {
                                    "@root": "2.16.840.1.113883.2.1.4.3",
                                    "id": gp["identifier"]["value"],
                                },
                            },
                        },
                    },
                },
            },
            "queryAck": {
                "queryId": query["queryId"],
                "queryResponseCode": {"@code": "OK"},
                "statusCode": {"@code": "deliveredResponse"},
            },
            "queryByParameter": query,
        },
    }
    header = create_header("urn:hl7-org:v3:PRPA_IN201306UV02", message_id)

    # pprint.pprint(patient)
    return xmltodict.unparse(create_envelope(header, body), pretty=True)


async def iti_39_response(message_id, document_id, document):
    registry_id = redis_client.get("registry")

    base64_bytes = base64.b64encode(document)
    body = {
        "RetrieveDocumentSetResponse": {
            "@xmlns": "urn:ihe:iti:xds-b:2007",
            "RegistryResponse": {
                "@status": "urn:oasis:names:tc:ebxml-regrep:ResponseStatusType:Success",
                "@xmlns": "urn:oasis:names:tc:ebxml-regrep:xsd:rs:3.0",
                "DocumentResponse": {
                    "HomeCommunityId": {"#text": f"urn:oid:{registry_id}"},
                    "RepositoryUniqueId": {"#text": registry_id},
                    "DocumentUniqueId": {"#text": document_id},
                    "mimeType": {"#text": "text/xml"},
                    "Document": base64_bytes.decode("ascii"),
                },
            },
        }
    }

    soap_response = create_envelope(
        create_header("urn:ihe:iti:2007:RetrieveDocumentSetResponse", message_id), body
    )

    with open(f"{document_id}.xml", "w") as output:
        output.write(xmltodict.unparse(soap_response, pretty=True))

    return xmltodict.unparse(soap_response, pretty=True)


async def iti_38_response(nhsno: int, queryid: str):

    body = {}
    body["AdhocQueryResponse"] = {
        "@status": "urn:oasis:names:tc:ebxml-regrep:ResponseStatusType:Success",
        "@xmlns": "urn:oasis:names:tc:ebxml-regrep:xsd:query:3.0",
    }

    # check the redis cash if there's an existing ccda
    docid = redis_client.get(nhsno)

    if docid is None:
        # no cached ccda
        async with AsyncClient() as client:
            r = await client.get(f"http://127.0.0.1:8000/gpconnect/{nhsno}")
            if r.status_code == 200:
                logging.info(f"used internal call for {nhsno}")
                docid = r.json()
                docid = docid["document_id"]
            else:
                body["AdhocQueryResponse"][
                    "@status"
                ] = "urn:oasis:names:tc:ebxml-regrep:ResponseStatusType:Failure"
                body["AdhocQueryResponse"]["RegistryErrorList"] = {
                    "@highestSeverity": "urn:oasis:names:tc:ebxml-regrep:ErrorSeverityType:Error",
                    "RegistryError": {
                        "@errorCode": "XDSRegistryError",
                        "@codeContext": f"Unable to locate SCR with NHS number {nhsno}",
                        "@location": "",
                        "@severity": "urn:oasis:names:tc:ebxml-regrep:ErrorSeverityType:Error",
                    },
                }

    if docid is not None:
        # add the ccda as registry object list

        # create list of slots
        slots = []
        classifications = []

        def create_slot(name: str, value) -> dict:
            slot_dict = {"@name": name, "ValueList": {"Value": {"#text": value}}}
            return slot_dict

        # slots.append(create_slot("creationTime", str(int(datetime.now().timestamp()))))
        # slots.append(create_slot("sourcePatientId", nhsno))
        slots.append(
            create_slot("sourcePatientId", f"{nhsno}^^^&2.16.840.1.113883.2.1.4.1&ISO")
        )
        slots.append(create_slot("languageCode", "en-GB"))
        # slots.append("entryUUID", f"urn:uuid:{uuid.uuid4()}")

        # No hash for on demand document
        # slots.append(create_slot("hash", "4cf4f82d78b5e2aac35c31bca8cb79fe6bd6a41e"))
        slots.append(create_slot("size", "1"))
        slots.append(create_slot("repositoryUniqueId", redis_client.get("registry")))
        object_id = "CCDA_01"
        body["AdhocQueryResponse"]["RegistryObjectList"] = {
            "@xmlns": "urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0",
            "ExtrinsicObject": {
                "@id": object_id,
                "@status": "urn:oasis:names:tc:ebxml-regrep:StatusType:Approved",
                "@objectType": "urn:uuid:34268e47-fdf5-41a6-ba33-82133c465248",  # On Demand
                "@mimeType": "text/xml",
                "Slot": slots,
                # UNIQUE ID SECTION
                "ExternalIdentifier": {
                    "@identificationScheme": "urn:uuid:2e82c1f6-a085-4c72-9da3-8640a32e42ab",
                    "@value": docid,
                    "@id": f"CCDA-{docid}",
                    "@registryObject": object_id,
                    "@objectType": "urn:oasis:names:tc:ebxml-regrep:ObjectType:RegistryObject:ExternalIdentifier",
                    "Name": {
                        "LocalizedString": {"@value": "XDSDocumentEntry.uniqueId"}
                    },
                },
            },
        }

    else:
        body["AdhocQueryResponse"]["RegistryObjectList"] = {}

    soap_response = create_envelope(
        create_header("urn:ihe:iti:2007:CrossGatewayQueryResponse", queryid), body
    )

    return xmltodict.unparse(soap_response, pretty=True)
