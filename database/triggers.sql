-- Triggers from doc/stage2_database_design-p2.md section 6.3.
-- Load with the mysql client, which understands the DELIMITER command:
--   mysql -u <user> -p <database> < database/triggers.sql

DELIMITER //

-- Only admins may review reports, and removing a report must record who and when.
CREATE TRIGGER trg_crashreport_review_bi
BEFORE INSERT ON CrashReport
FOR EACH ROW
BEGIN
  IF NEW.reviewed_by IS NOT NULL AND
     (SELECT role FROM AppUser WHERE user_id = NEW.reviewed_by) <> 'admin' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'reviewed_by must reference an admin';
  END IF;
  IF NEW.status = 'removed' AND (NEW.reviewed_by IS NULL OR NEW.reviewed_at IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'removing a report requires reviewed_by and reviewed_at';
  END IF;
END//

CREATE TRIGGER trg_crashreport_review_bu
BEFORE UPDATE ON CrashReport
FOR EACH ROW
BEGIN
  IF NEW.reviewed_by IS NOT NULL AND NOT (NEW.reviewed_by <=> OLD.reviewed_by) AND
     (SELECT role FROM AppUser WHERE user_id = NEW.reviewed_by) <> 'admin' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'reviewed_by must reference an admin';
  END IF;
  IF NEW.status = 'removed' AND OLD.status <> 'removed' AND
     (NEW.reviewed_by IS NULL OR NEW.reviewed_at IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'removing a report requires reviewed_by and reviewed_at';
  END IF;
END//

-- A person's vehicle must exist (veh_no 0 means a non-motorist).
CREATE TRIGGER trg_person_vehicle_bi
BEFORE INSERT ON Person
FOR EACH ROW
BEGIN
  IF NEW.veh_no <> 0 AND NOT EXISTS (
       SELECT 1 FROM Vehicle v
       WHERE v.data_year = NEW.data_year AND v.st_case = NEW.st_case AND v.veh_no = NEW.veh_no) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'person references a vehicle that does not exist';
  END IF;
END//

CREATE TRIGGER trg_person_vehicle_bu
BEFORE UPDATE ON Person
FOR EACH ROW
BEGIN
  IF NEW.veh_no <> 0 AND NOT EXISTS (
       SELECT 1 FROM Vehicle v
       WHERE v.data_year = NEW.data_year AND v.st_case = NEW.st_case AND v.veh_no = NEW.veh_no) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'person references a vehicle that does not exist';
  END IF;
END//

-- A chosen route option must have been offered.
CREATE TRIGGER trg_routerequest_choice_bi
BEFORE INSERT ON RouteRequest
FOR EACH ROW
BEGIN
  IF NEW.chosen_option IS NOT NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'chosen_option must be NULL until options are offered';
  END IF;
END//

CREATE TRIGGER trg_routerequest_choice_bu
BEFORE UPDATE ON RouteRequest
FOR EACH ROW
BEGIN
  IF NEW.chosen_option IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM RouteOption o
       WHERE o.route_id = NEW.route_id AND o.option_type = NEW.chosen_option) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'chosen_option was not offered for this route';
  END IF;
END//

DELIMITER ;
